import asyncio
import uuid
import json
import logging
import httpx
from threading import Thread
from fastapi import FastAPI, Request
import uvicorn
import time

# ==================== CONFIG ====================
GATEWAY_URL = "http://localhost:8000/api/v1/scrape"
CALLBACK_HOST = "0.0.0.0"
CALLBACK_PORT = 9999
NUM_QUERIES = 5 # Using 5 for a clean test of 1 per browser (or 2-per-worker in reality)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger("LoadTester")

app = FastAPI()
received_jobs = set()
finish_event = asyncio.Event()

@app.post("/callback")
async def receive_callback(request: Request):
    payload = await request.json()
    job_id = payload.get('job_id')
    received_jobs.add(job_id)
    logger.info(f"✅ Callback Received ({len(received_jobs)}/{NUM_QUERIES}): {job_id}")
    if len(received_jobs) >= NUM_QUERIES:
        finish_event.set()
    return {"status": "ok"}

def start_server():
    uvicorn.run(app, host=CALLBACK_HOST, port=CALLBACK_PORT, log_level="error")

async def submit_job(client, job_id):
    payload = {
        "job_id": job_id,
        "query": "What is the capital of India?",
        "location": "India",
        "callback_url": f"http://host.docker.internal:{CALLBACK_PORT}/callback"
    }
    try:
        resp = await client.post(GATEWAY_URL, json=payload, timeout=10)
        if resp.status_code == 202:
            logger.info(f"📤 Job {job_id} Accepted")
        else:
            logger.error(f"❌ Job {job_id} Rejected: {resp.text}")
    except Exception as e:
        logger.error(f"❌ Connection Error for {job_id}: {e}")

async def main():
    logger.info(f"🚀 Firing {NUM_QUERIES} queries concurrently...")
    
    # Start Fast API in background
    server_thread = Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Wait for server to boot
    await asyncio.sleep(2)

    async with httpx.AsyncClient() as client:
        start_time = time.time()
        
        # Submit all at once
        tasks = [submit_job(client, f"stress-test-{i}-{uuid.uuid4().hex[:4]}") for i in range(NUM_QUERIES)]
        await asyncio.gather(*tasks)
        
        logger.info("📡 All 5 queries sent! Worker cluster is now scraping in parallel...")
        
        try:
            await asyncio.wait_for(finish_event.wait(), timeout=180)
            duration = time.time() - start_time
            logger.info(f"🎉 SUCCESS! Total time for {NUM_QUERIES} queries: {duration:.2f}s")
        except asyncio.TimeoutError:
            logger.error(f"⏰ TIMEOUT: Only {len(received_jobs)}/{NUM_QUERIES} callbacks received.")

if __name__ == "__main__":
    asyncio.run(main())
