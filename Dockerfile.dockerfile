# 1. Start with a Python base image
FROM python:3.11-slim

# 2. Set up a working directory
WORKDIR /app

# 3. Install the system dependencies Playwright needs for Chromium
# Clean up apt cache afterwards to keep the image smaller
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libasound2 && \
    rm -rf /var/lib/apt/lists/*

# 4. Copy and install your Python app's requirements FIRST
# This ensures the correct Playwright version is installed before downloading browsers
# Using --no-cache-dir reduces image size slightly
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. NOW, install the Playwright browser using the just-installed package
# Using --with-deps installs browser dependencies too, belt-and-braces approach
# Clean up download cache after install
RUN playwright install --with-deps chromium \
    && rm -rf /root/.cache/ms-playwright/download

# 6. Copy your application code into the container
# This comes later so Docker uses the cache for previous layers if code changes
COPY main.py .

# 7. Tell the container what command to run on start
# - Uvicorn runs the FastAPI app ('main:app' assumes your file is main.py and FastAPI instance is 'app')
# - --host 0.0.0.0 makes it listen on all network interfaces (required in containers)
# - --port 8000 specifies the port (Railway typically detects this or uses a PORT env var)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
