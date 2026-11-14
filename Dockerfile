FROM python:3.11-slim-bookworm
WORKDIR /app

# Install Debian runtime libraries explicitly; avoid Playwright's --with-deps.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    fonts-noto-core fonts-dejavu-core fonts-unifont \
    xvfb xauth x11vnc novnc websockify nginx apache2-utils supervisor \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
    libatspi2.0-0 libwayland-client0 libxshmfence1 libx11-xcb1 libxcb1 \
    libxext6 libx11-6 libglib2.0-0 libpango-1.0-0 libcairo2 libdbus-1-3 \
    libexpat1 libfontconfig1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY . .
RUN chmod +x /app/entrypoint.sh \
    && rm -f /etc/nginx/sites-enabled/default \
    && ln -sf /app/nginx.conf /etc/nginx/nginx.conf

ENV DISPLAY=:99
CMD ["/app/entrypoint.sh"]
