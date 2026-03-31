import requests
import json

url = "http://localhost:8000/api/v1/scrape"
payload = {
    "job_id": "test-dedup-check-FINAL",
    "query": "What is the capital of France?",
    "product_id": "b36b116e-0c19-4fa0-b669-835bd76c820e",
    "callback_url": "http://host.docker.internal:9999/callback"
}

headers = {
    "Content-Type": "application/json"
}

try:
    response = requests.post(url, data=json.dumps(payload), headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
