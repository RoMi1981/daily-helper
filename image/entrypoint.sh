#!/bin/sh
set -e

# Adjust UID/GID at runtime if PUID/PGID differ from build-time defaults
CURRENT_GID=$(id -g appuser)
CURRENT_UID=$(id -u appuser)
if [ "${PGID}" != "${CURRENT_GID}" ]; then
    groupmod -g "${PGID}" appuser
fi
if [ "${PUID}" != "${CURRENT_UID}" ]; then
    usermod -u "${PUID}" appuser
fi

# Fix /data ownership on first start (volume is created by Docker as root)
mkdir -p /data/repos /data/tls
chown -R appuser:appuser /data /app

# Determine TLS mode and prepare cert files
TLS_MODE=$(cd /app && python3 -m core.prepare_tls 2>/dev/null || echo "http")

case "$TLS_MODE" in
  selfsigned)
    exec gosu appuser uvicorn main:app --host 0.0.0.0 --port 8080 \
      --ssl-keyfile /data/tls/server.key \
      --ssl-certfile /data/tls/server.crt
    ;;
  custom)
    exec gosu appuser uvicorn main:app --host 0.0.0.0 --port 8080 \
      --ssl-keyfile /data/tls/custom.key \
      --ssl-certfile /data/tls/custom.crt
    ;;
  *)
    exec gosu appuser uvicorn main:app --host 0.0.0.0 --port 8080
    ;;
esac
