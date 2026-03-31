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
NUM_QUERIES = 20

TEST_QUERIES = [
    "What is the current price of Bitcoin?",
    "How to make a perfect Neapolitan pizza?",
    "Latest breakthroughs in Quantum Computing 2024",
    "Best places to visit in Japan during spring",
    "How does a transformer neural network work?",
    "Benefits of Mediterranean diet for heart health",
    "History of the Ottoman Empire summary",
    "Top 5 electric SUVs with highest range in 2024",
    "Who won the most Oscars in history?",
    "NASA's next mission to Mars details"
]

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

async def submit_job(client, job_id, query):
    payload = {
        "job_id": job_id,
        "product_id": "b36b116e-0c19-4fa0-b669-835bd76c820e", # User provided product_id
        "query": query,
        "location": "India",
        "callback_url": f"http://host.docker.internal:{CALLBACK_PORT}/callback"
    }
    try:
        resp = await client.post(GATEWAY_URL, json=payload, timeout=10)
        if resp.status_code == 202:
            logger.info(f"📤 Job {job_id} Accepted: {query[:30]}...")
        else:
            logger.error(f"❌ Job {job_id} Rejected: {resp.text}")
    except Exception as e:
        logger.error(f"❌ Connection Error for {job_id}: {e}")

async def main():
    logger.info(f"🚀 Firing {NUM_QUERIES} unique queries concurrently...")
    
    # Start Fast API in background
    server_thread = Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Wait for server to boot
    await asyncio.sleep(2)

    async with httpx.AsyncClient() as client:
        start_time = time.time()
        
        # Submit unique queries
        tasks = []
        for i in range(NUM_QUERIES):
            query = TEST_QUERIES[i % len(TEST_QUERIES)]
            job_id = f"stress-test-{i}-{uuid.uuid4().hex[:4]}"
            tasks.append(submit_job(client, job_id, query))
        
        await asyncio.gather(*tasks)
        
        logger.info(f"📡 All {NUM_QUERIES} queries sent! Worker cluster is now scraping in parallel...")
        
        try:
            # Increased timeout to 300s because Perplexity is much slower with these jitter/humanization fixes
            await asyncio.wait_for(finish_event.wait(), timeout=300)
            duration = time.time() - start_time
            logger.info(f"🎉 SUCCESS! Total time for {NUM_QUERIES} queries: {duration:.2f}s")
        except asyncio.TimeoutError:
            logger.error(f"⏰ TIMEOUT: Only {len(received_jobs)}/{NUM_QUERIES} callbacks received.")

if __name__ == "__main__":
    asyncio.run(main())
