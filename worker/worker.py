import asyncio
import json
import logging
import os
import random
import signal
import sys
from datetime import datetime
from typing import Optional

import aio_pika
import httpx
from supabase import create_client, Client

from scraper import BrowserManager, PerplexityScraper

# ==================== LOGGING ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ==================== CONFIG ====================

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
WORKER_CONCURRENCY = int(os.environ.get("WORKER_CONCURRENCY", "5"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))
CALLBACK_TIMEOUT_SEC = 30
CALLBACK_MAX_ATTEMPTS = 3

# ==================== SHARED STATE ====================

semaphore = asyncio.Semaphore(WORKER_CONCURRENCY)
browser_manager = BrowserManager()
shutdown_event = asyncio.Event()

# ==================== DATABASE ====================

async def update_status(client: Client, job_id: str, status: str):
    """Update job status in Supabase using the library.
    Silent on error to prevent worker crash."""
    try:
        # data = client.table("processed_jobs").update({"status": status}).eq("job_id", job_id).execute()
        # Since supabase-py is synchronous for some versions or prefers a specific pattern,
        # we'll use a standard execute call.
        client.table("processed_jobs").update({"status": status}).eq("job_id", job_id).execute()
        log.info(f"[{job_id}] Status → {status}")
    except Exception as e:
        log.error(f"[{job_id}] Failed to update status to {status}: {e}")


# ==================== CALLBACK ====================

async def deliver_callback(job_id: str, callback_url: str, payload: dict) -> bool:
    """POST scrape result to the caller's callback URL."""
    async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT_SEC) as client:
        for attempt in range(1, CALLBACK_MAX_ATTEMPTS + 1):
            try:
                resp = await client.post(callback_url, json=payload)
                if resp.status_code < 500:
                    log.info(f"[{job_id}] Callback delivered → {resp.status_code}")
                    return True
                log.warning(f"[{job_id}] Callback attempt {attempt} got {resp.status_code}")
            except httpx.TimeoutException:
                log.warning(f"[{job_id}] Callback attempt {attempt} timed out")
            except Exception as e:
                log.warning(f"[{job_id}] Callback attempt {attempt} error: {e}")

            if attempt < CALLBACK_MAX_ATTEMPTS:
                wait = 2 ** (attempt - 1)
                await asyncio.sleep(wait)

    log.error(f"[{job_id}] Callback delivery failed after {CALLBACK_MAX_ATTEMPTS} attempts")
    return False


# ==================== BROWSER HEALTH ====================

async def ensure_browser_healthy():
    """If the browser has died, restart it."""
    if not await browser_manager.is_healthy():
        log.warning("Browser unhealthy — restarting...")
        await browser_manager.stop()
        await browser_manager.start()
        log.info("Browser restarted")


# ==================== JOB PROCESSING ====================

async def process_job(message: aio_pika.IncomingMessage, client: Client, channel: aio_pika.Channel):
    """Full lifecycle for one job using Supabase Client."""
    job_id: Optional[str] = None

    async with semaphore:
        try:
            payload = json.loads(message.body)
            job_id = payload["job_id"]
            query = payload["query"]
            location = payload.get("location", "India")
            callback_url = payload["callback_url"]

            retry_count = int(message.headers.get("x-retry-count", 0)) if message.headers else 0
            log.info(f"[{job_id}] Starting — query: {query!r}, location: {location}, attempt: {retry_count + 1}/{MAX_RETRIES + 1}")

            await update_status(client, job_id, "processing")
            await ensure_browser_healthy()

            scraper = PerplexityScraper()
            user_agent = random.choice(scraper.user_agents)
            page, context = await browser_manager.create_page(location, user_agent)

            try:
                result = await scraper.scrape(page, query)
            finally:
                try:
                    await context.close()
                except Exception:
                    pass

            callback_payload = {
                "job_id": job_id,
                "success": result.success,
                "query": result.query,
                "ai_overview_text": result.ai_overview_text,
                "source_links": [
                    {
                        "text": link.text,
                        "url": link.url,
                        "raw_url": link.raw_url,
                        "highlight_fragment": link.highlight_fragment,
                        "related_claim": link.related_claim,
                        "extraction_order": link.extraction_order,
                    }
                    for link in result.source_links
                ],
                "timestamp": result.timestamp,
                "error_message": result.error_message,
            }

            await deliver_callback(job_id, callback_url, callback_payload)

            final_status = "completed" if result.success else "failed"
            await update_status(client, job_id, final_status)

            await message.ack()
            log.info(f"[{job_id}] Done — {final_status}")

        except Exception as e:
            log.error(f"[{job_id}] Processing error: {e}")
            retry_count = int(message.headers.get("x-retry-count", 0)) if message.headers else 0

            if retry_count < MAX_RETRIES:
                next_retry = retry_count + 1
                wait = 5 * next_retry
                log.info(f"[{job_id}] Retrying in {wait}s (attempt {next_retry}/{MAX_RETRIES})")
                await asyncio.sleep(wait)

                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=message.body,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        headers={"x-retry-count": next_retry},
                    ),
                    routing_key="perplexity_jobs",
                )
                await message.ack()
            else:
                log.error(f"[{job_id}] Exhausted {MAX_RETRIES} retries — marking failed")
                if job_id:
                    await update_status(client, job_id, "failed")
                await message.ack()


# ==================== CONSUMER LOOP ====================

async def consume(client: Client):
    """Main consumer loop with automatic reconnection."""
    while not shutdown_event.is_set():
        connection: Optional[aio_pika.RobustConnection] = None
        try:
            log.info("Connecting to RabbitMQ...")
            connection = await aio_pika.connect_robust(RABBITMQ_URL, reconnect_interval=5)
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=WORKER_CONCURRENCY)

            job_queue = await channel.declare_queue("perplexity_jobs", durable=True)
            await channel.declare_queue("perplexity_dead_letter", durable=True)

            log.info(f"Ready — consuming with concurrency={WORKER_CONCURRENCY}")

            async def on_message(msg: aio_pika.IncomingMessage):
                asyncio.create_task(process_job(msg, client, channel))

            await job_queue.consume(on_message)
            await shutdown_event.wait()

        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"RabbitMQ error: {e} — reconnecting in 5s...")
            await asyncio.sleep(5)
        finally:
            if connection and not connection.is_closed:
                await connection.close()


# ==================== GRACEFUL SHUTDOWN ====================

def handle_shutdown(sig):
    log.info(f"Received {sig.name} — shutting down gracefully...")
    shutdown_event.set()


# ==================== ENTRYPOINT ====================

async def main():
    log.info("Worker starting with Supabase library...")
    
    # Initialize Supabase Client
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("Supabase library client initialized")
    except Exception as e:
        log.error(f"Failed to initialize Supabase client: {e}")
        sys.exit(1)

    await browser_manager.start()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: handle_shutdown(s))

    try:
        await consume(supabase_client)
    finally:
        await browser_manager.stop()
        log.info("Worker stopped cleanly")


if __name__ == "__main__":
    asyncio.run(main())