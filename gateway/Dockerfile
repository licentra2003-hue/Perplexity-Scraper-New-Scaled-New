# ── Stage 1: Build ──────────────────────────────────────────────
FROM golang:1.22-alpine AS builder

WORKDIR /build

# Download dependencies first (cached layer unless go.mod/go.sum change)
COPY go.mod go.sum ./
RUN go mod download

# Build a statically linked binary — no libc needed in the final image
COPY main.go .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o gateway .

# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM alpine:3.20

# ca-certificates is needed for HTTPS calls (Supabase, etc.)
RUN apk add --no-cache ca-certificates tzdata

WORKDIR /app
COPY --from=builder /build/gateway .

# Non-root user for security
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
USER appuser

EXPOSE 8000

CMD ["./gateway"]