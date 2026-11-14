FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-noto-core fonts-dejavu-core xvfb xauth x11vnc novnc websockify nginx apache2-utils supervisor \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install --with-deps chromium
COPY . .
RUN chmod +x /app/entrypoint.sh && rm -f /etc/nginx/sites-enabled/default && ln -sf /app/nginx.conf /etc/nginx/nginx.conf
ENV DISPLAY=:99
CMD ["/app/entrypoint.sh"]
