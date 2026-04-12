# bookworm (Debian 12) أكثر استقراراً من trixie للـ packages
FROM python:3.11-slim-bookworm

RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    xvfb \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgdk-pixbuf2.0-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    --no-install-recommends && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY opgg_bot.py .

ENV CHROMIUM_PATH=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV DISPLAY=:99

# Xvfb بيشغل شاشة وهمية → sleep ثانية يديه وقت يبدأ → بعدين البوت
CMD ["sh", "-c", "Xvfb :99 -screen 0 1920x1080x24 & sleep 1 && python opgg_bot.py"]
