import asyncio
import uuid
import json
import logging
import httpx
from fastapi import FastAPI, Request
import uvicorn
from threading import Thread

# ==================== CONFIG ====================
GATEWAY_URL = "http://localhost:8000/api/v1/scrape"
STATUS_URL = "http://localhost:8000/api/v1/job-status/{job_id}"
CALLBACK_HOST = "0.0.0.0"
CALLBACK_PORT = 9999
CALLBACK_URL = f"http://host.docker.internal:{CALLBACK_PORT}/callback"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ScraperTester")

# ==================== CALLBACK LISTENER ====================
app = FastAPI()
callback_received = asyncio.Event()
received_payload = {}

@app.post("/callback")
async def receive_callback(request: Request):
    global received_payload
    payload = await request.json()
    logger.info(f"✅ Received Callback for Job: {payload.get('job_id')}")
    received_payload = payload
    callback_received.set()
    return {"status": "ok"}

def start_callback_server():
    uvicorn.run(app, host=CALLBACK_HOST, port=CALLBACK_PORT, log_level="error")

# ==================== TEST FLOW ====================
async def run_test():
    job_id = f"test-job-{uuid.uuid4().hex[:8]}"
    query = "What is the capital of India?"
    
    logger.info(f"🚀 Starting test job: {job_id}")
    
    async with httpx.AsyncClient() as client:
        # 1. Submit job to gateway
        try:
            payload = {
                "job_id": job_id,
                "product_id": "b36b116e-0c19-4fa0-b669-835bd76c820e", # User provided product_id
                "query": query,
                "location": "India",
                "callback_url": CALLBACK_URL
            }
            resp = await client.post(GATEWAY_URL, json=payload, timeout=10)
            
            if resp.status_code == 202:
                logger.info(f"📤 Job submitted successfully: {resp.json()}")
            else:
                logger.error(f"❌ Submission failed ({resp.status_code}): {resp.text}")
                return

        except Exception as e:
            logger.error(f"❌ Connection error to Gateway: {e}")
            logger.warning("Ensure Docker containers are running with 'docker-compose up --build'")
            return

        # 2. Wait for callback with timeout (Perplexity can take 30-60s)
        logger.info("⏳ Waiting for callback from worker (timeout: 120s)...")
        try:
            await asyncio.wait_for(callback_received.wait(), timeout=120)
            logger.info("🎯 CALLBACK RECEIVED!")
            
            # 3. Validate Result
            success = received_payload.get("success")
            if success:
                logger.info("✨ SCRAPE SUCCESSFUL!")
                logger.info(f"🤖 AI Overview: {received_payload.get('ai_overview_text')[:200]}...")
                logger.info(f"🔗 Source count: {len(received_payload.get('source_links', []))}")
            else:
                logger.error(f"💥 SCRAPE FAILED: {received_payload.get('error_message')}")

            # 4. Check status endpoint
            status_resp = await client.get(STATUS_URL.format(job_id=job_id))
            logger.info(f"📊 Final status from Gateway: {status_resp.json()}")

        except asyncio.TimeoutError:
            logger.error("⏰ TIMEOUT: Never received callback. Check worker logs.")

if __name__ == "__main__":
    # Start the local callback server in a background thread
    server_thread = Thread(target=start_callback_server, daemon=True)
    server_thread.start()
    
    # Run the async test client
    asyncio.run(run_test())
