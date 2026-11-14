#!/bin/sh
set -eu
: "${BROWSER_ACCESS_USER:=flow}"
: "${BROWSER_ACCESS_PASSWORD:?Set BROWSER_ACCESS_PASSWORD in Railway Variables}"
printf '%s:%s\n' "$BROWSER_ACCESS_USER" "$BROWSER_ACCESS_PASSWORD" | htpasswd -ci /etc/nginx/.htpasswd "$BROWSER_ACCESS_USER"
chmod 640 /etc/nginx/.htpasswd\nPORT="${PORT:-8080}"\nsed -i "s/listen 8080;/listen ${PORT};/" /app/nginx.conf
exec /usr/bin/supervisord -c /app/supervisord.conf
