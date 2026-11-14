#!/bin/sh
set -eu
: "${BROWSER_ACCESS_USER:=flow}"
: "${BROWSER_ACCESS_PASSWORD:?Set BROWSER_ACCESS_PASSWORD in Railway Variables}"
printf '%s\n' "$BROWSER_ACCESS_PASSWORD" | htpasswd -ci /etc/nginx/.htpasswd "$BROWSER_ACCESS_USER"
chown www-data:www-data /etc/nginx/.htpasswd
chmod 640 /etc/nginx/.htpasswd
PORT="${PORT:-8080}"
sed -i "s/listen 8080;/listen ${PORT};/" /app/nginx.conf
exec /usr/bin/supervisord -c /app/supervisord.conf
