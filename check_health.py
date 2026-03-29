import urllib.request
import time

def check():
    for i in range(30):
        try:
            with urllib.request.urlopen("http://localhost:8000/api/v1/health", timeout=2) as response:
                print(f"Health check: {response.getcode()} - {response.read().decode()}")
                return True
        except Exception as e:
            print(f"Waiting for Gateway... attempt {i+1}/30: {e}")
        time.sleep(2)
    return False

if __name__ == "__main__":
    check()
