# Use official Python slim image (bookworm = Debian 12)
FROM python:3.12-slim-bookworm

# Install system dependencies for Chromium + fonts (needed for rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    fonts-liberation \
    libappindicator3-1 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables so Selenium finds Chrome & driver
ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver \
    PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Copy and install Python dependencies first (caching layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your app
COPY . .

# Expose Streamlit port
EXPOSE 8501

# Run Streamlit (binds to 0.0.0.0 so external access works)
CMD ["streamlit", "run", "reagent_quote.py", "--server.port=8501", "--server.address=0.0.0.0"]
