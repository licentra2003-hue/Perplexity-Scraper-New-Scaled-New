package main

import (
	"context"
	"encoding/json"
	"log"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/supabase-community/supabase-go"
	amqp "github.com/rabbitmq/amqp091-go"
)

// ==================== CONFIG ====================

type Config struct {
	RabbitMQURL string
	SupabaseURL string
	SupabaseKey string
	Port        string
}

func loadConfig() Config {
	return Config{
		RabbitMQURL: mustEnv("RABBITMQ_URL"),
		SupabaseURL: mustEnv("SUPABASE_URL"),
		SupabaseKey: mustEnv("SUPABASE_KEY"),
		Port:        getEnv("PORT", "8000"),
	}
}

func mustEnv(key string) string {
	v := os.Getenv(key)
	if v == "" {
		log.Fatalf("Missing required environment variable: %s", key)
	}
	return v
}

func getEnv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

// ==================== MODELS ====================

type ScrapeRequest struct {
	JobID       string `json:"job_id"`
	ProductID   string `json:"product_id"`
	Query       string `json:"query"`
	Location    string `json:"location"`
	CallbackURL string `json:"callback_url"`
}

type ScrapeResponse struct {
	JobID   string `json:"job_id"`
	Status  string `json:"status"`
	Message string `json:"message"`
}

type JobStatusResponse struct {
	JobID  string `json:"job_id"`
	Status string `json:"status"`
}

// ==================== APP ====================

type App struct {
	cfg     Config
	sb      *supabase.Client
	amqp    *amqp.Connection
	channel *amqp.Channel
}

func NewApp(cfg Config) *App {
	return &App{cfg: cfg}
}

func (a *App) Connect(ctx context.Context) error {
	// --- Supabase Library ---
	sb, err := supabase.NewClient(a.cfg.SupabaseURL, a.cfg.SupabaseKey, nil)
	if err != nil {
		return err
	}
	a.sb = sb
	log.Println("Initialized Supabase Client")

	// --- RabbitMQ ---
	conn, err := amqp.Dial(a.cfg.RabbitMQURL)
	if err != nil {
		return err
	}
	ch, err := conn.Channel()
	if err != nil {
		return err
	}

	// Declare queues — idempotent, safe on restart
	for _, q := range []string{"perplexity_jobs", "perplexity_dead_letter"} {
		if _, err := ch.QueueDeclare(q, true, false, false, false, nil); err != nil {
			return err
		}
	}

	a.amqp = conn
	a.channel = ch
	log.Println("Connected to RabbitMQ")

	return nil
}

func (a *App) Close() {
	if a.channel != nil {
		a.channel.Close()
	}
	if a.amqp != nil {
		a.amqp.Close()
	}
}

// ==================== HANDLERS ====================

// POST /api/v1/scrape
func (a *App) handleScrape(c *fiber.Ctx) error {
	var req ScrapeRequest
	if err := c.BodyParser(&req); err != nil {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"error": "invalid request body",
		})
	}

	// Validate required fields
	if req.JobID == "" || req.Query == "" || req.CallbackURL == "" {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"error": "job_id, query, and callback_url are required",
		})
	}
	if req.Location == "" {
		req.Location = "India"
	}


	// --- Deduplication check ---
	var results []struct {
		Status string `json:"status"`
	}
	_, err := a.sb.From("processed_jobs").Select("status", "exact", false).Eq("job_id", req.JobID).ExecuteTo(&results)

	if err == nil && len(results) > 0 {
		return c.Status(fiber.StatusConflict).JSON(fiber.Map{
			"error":  "job already exists",
			"job_id": req.JobID,
			"status": results[0].Status,
		})
	}

	// --- Insert job into Supabase ---
	row := map[string]interface{}{
		"job_id":       req.JobID,
		"status":       "queued",
		"callback_url": req.CallbackURL,
		"engine":       "perplexity",
	}

	log.Printf("[%s] Registering job in DB: %+v", req.JobID, row)

	body, count, err := a.sb.From("processed_jobs").Insert(row, false, "", "representation", "").Execute()
	if err != nil {
		log.Printf("[%s] [DB ERROR] Insert failed: %v | Body: %s", req.JobID, err, string(body))
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": "failed to register job",
		})
	}
	log.Printf("[%s] [DB OK] Job registered (count: %d)", req.JobID, count)

	// --- Publish to RabbitMQ ---
	body, err = json.Marshal(map[string]string{
		"job_id":       req.JobID,
		"product_id":   req.ProductID,
		"query":        req.Query,
		"location":     req.Location,
		"callback_url": req.CallbackURL,
	})
	if err != nil {
		log.Printf("[%s] Failed to marshal payload: %v", req.JobID, err)
		return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
			"error": "failed to encode job",
		})
	}

	err = a.channel.Publish(
		"",                // default exchange
		"perplexity_jobs", // routing key = queue name
		false,
		false,
		amqp.Publishing{
			ContentType:  "application/json",
			DeliveryMode: amqp.Persistent,
			Body:         body,
		},
	)
	if err != nil {
		log.Printf("[%s] Failed to publish: %v", req.JobID, err)
		// rollback
		return c.Status(500).JSON(fiber.Map{"error": "failed to queue job"})
	}
	log.Printf("[%s] Job published to RabbitMQ", req.JobID)

	log.Printf("[%s] Accepted — query: %q, location: %s", req.JobID, req.Query, req.Location)

	return c.Status(fiber.StatusAccepted).JSON(ScrapeResponse{
		JobID:   req.JobID,
		Status:  "queued",
		Message: "Job accepted and queued for processing",
	})
}

// GET /api/v1/job-status/:jobId
func (a *App) handleJobStatus(c *fiber.Ctx) error {
	jobID := c.Params("jobId")
	if jobID == "" {
		return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{
			"error": "job_id is required",
		})
	}

	var results []struct {
		Status string `json:"status"`
	}
	_, err := a.sb.From("processed_jobs").Select("status", "exact", false).Eq("job_id", jobID).ExecuteTo(&results)

	if err != nil || len(results) == 0 {
		return c.Status(fiber.StatusNotFound).JSON(fiber.Map{
			"error":  "job not found",
			"job_id": jobID,
		})
	}
	status := results[0].Status

	return c.JSON(JobStatusResponse{
		JobID:  jobID,
		Status: status,
	})
}

// GET /health
func (a *App) handleHealth(c *fiber.Ctx) error {
	dbOK := a.sb != nil
	mqOK := !a.amqp.IsClosed()

	status := "healthy"
	httpStatus := fiber.StatusOK
	if !dbOK || !mqOK {
		status = "degraded"
		httpStatus = fiber.StatusServiceUnavailable
	}

	return c.Status(httpStatus).JSON(fiber.Map{
		"status":   status,
		"database": dbOK,
		"rabbitmq": mqOK,
	})
}

// ==================== DEAD LETTER CONSUMER ====================

// consumeDeadLetter runs in the background and marks dead-lettered jobs
// as failed in Supabase for any that the workers couldn't handle.
func (a *App) consumeDeadLetter(ctx context.Context) {
	ch, err := a.amqp.Channel()
	if err != nil {
		log.Printf("Dead letter consumer: failed to open channel: %v", err)
		return
	}
	defer ch.Close()

	msgs, err := ch.Consume(
		"perplexity_dead_letter",
		"gateway-dlq-consumer",
		false, // manual ack
		false,
		false,
		false,
		nil,
	)
	if err != nil {
		log.Printf("Dead letter consumer: failed to start consuming: %v", err)
		return
	}

	log.Println("Dead letter consumer started")

	for {
		select {
		case <-ctx.Done():
			return
		case msg, ok := <-msgs:
			if !ok {
				return
			}

			var payload map[string]interface{}
			if err := json.Unmarshal(msg.Body, &payload); err != nil {
				log.Printf("Dead letter: malformed message: %v", err)
				_ = msg.Ack(false)
				continue
			}

			jobID, _ := payload["job_id"].(string)
			if jobID != "" {
				_, _, err := a.sb.From("processed_jobs").Update(map[string]interface{}{"status": "failed"}, "exact", "").Eq("job_id", jobID).Execute()
				if err != nil {
					log.Printf("Dead letter: failed to mark job %s as failed: %v", jobID, err)
				} else {
					log.Printf("Dead letter: marked job %s as failed", jobID)
				}
			}

			_ = msg.Ack(false)
		}
	}
}

// ==================== MAIN ====================

func main() {
	cfg := loadConfig()
	app := NewApp(cfg)

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Connect to dependencies
	if err := app.Connect(ctx); err != nil {
		log.Fatalf("Failed to connect: %v", err)
	}
	defer app.Close()

	// Start dead letter consumer in background
	go app.consumeDeadLetter(ctx)

	// Build Fiber app
	fiberApp := fiber.New(fiber.Config{
		ReadTimeout:  30 * time.Second,
		WriteTimeout: 30 * time.Second,
		// Don't expose stack traces to clients
		ErrorHandler: func(c *fiber.Ctx, err error) error {
			log.Printf("Unhandled error: %v", err)
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{
				"error": "internal server error",
			})
		},
	})

	fiberApp.Use(recover.New())
	fiberApp.Use(logger.New(logger.Config{
		Format: "${time} ${method} ${path} → ${status} (${latency})\n",
	}))

	// Routes
	fiberApp.Get("/health", app.handleHealth)

	v1 := fiberApp.Group("/api/v1")
	v1.Post("/scrape", app.handleScrape)
	v1.Get("/job-status/:job_id", app.handleJobStatus)

	// Start server in a goroutine so shutdown can be handled cleanly
	go func() {
		addr := ":" + cfg.Port
		log.Printf("Gateway listening on %s", addr)
		if err := fiberApp.Listen(addr); err != nil {
			log.Printf("Server stopped: %v", err)
		}
	}()

	// Wait for shutdown signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGTERM, syscall.SIGINT)
	<-quit

	log.Println("Shutting down gateway...")
	cancel()
	_ = fiberApp.Shutdown()
	log.Println("Gateway stopped cleanly")
}
