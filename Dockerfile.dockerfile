# 1. Start with a Python base image
FROM python:3.11-slim

# 2. Set up a working directory
WORKDIR /app

# 3. Install the system dependencies Playwright needs
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
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. NOW, install the Playwright browser using the just-installed package
RUN playwright install chromium

# 6. Copy your application code into the container
COPY main.py .

# 7. Tell the container what command to run on start
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
