# 1. Start with a Python base image
FROM python:3.11-slim

# 2. Set up a working directory
WORKDIR /app

# 3. Install the system dependencies Playwright needs
# This is the step that makes Docker necessary
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

# 4. Install the Playwright browser (Chromium)
# We run this BEFORE installing Python requirements for better caching
RUN pip install playwright
RUN playwright install chromium

# 5. Copy and install your Python app's requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 6. Copy your application code into the container
COPY main.py .

# 7. Tell the container what command to run on start
# This exposes your app on port 8000, which Railway will detect
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
