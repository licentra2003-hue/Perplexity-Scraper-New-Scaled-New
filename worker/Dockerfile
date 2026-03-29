# Python worker — no web server, just a RabbitMQ consumer loop
FROM python:3.11-slim

WORKDIR /app

# System dependencies Playwright/Chromium needs
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

# Install Python dependencies before copying app code
# (Docker layer cache: only re-runs if requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium via Playwright
RUN playwright install --with-deps chromium \
    && rm -rf /root/.cache/ms-playwright/download

# Copy application code last — most likely to change
COPY scraper.py .
COPY worker.py .

# This is a consumer process, not a web server — run worker.py directly
CMD ["python", "-u", "worker.py"]