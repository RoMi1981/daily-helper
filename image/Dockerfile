FROM python:3.12-slim

# Git for the storage driver, gosu for privilege drop in entrypoint
RUN apt-get update && apt-get install -y --no-install-recommends git openssh-client gosu curl gnupg \
    && rm -rf /var/lib/apt/lists/*

ARG GIT_COMMIT=dev
ENV APP_VERSION=${GIT_COMMIT}

ARG PUID=1005
ARG PGID=1005
ENV PUID=${PUID}
ENV PGID=${PGID}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Non-root user; UID/GID default to 1005, overridable at build time via --build-arg or at runtime via PUID/PGID env vars
RUN groupadd -g ${PGID} appuser && useradd -u ${PUID} -g ${PGID} -m appuser \
    && chown -R appuser:appuser /app

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -fsk --max-time 5 https://localhost:8080/health 2>/dev/null \
     || curl -fs  --max-time 5 http://localhost:8080/health  2>/dev/null \
     || exit 1
ENTRYPOINT ["/entrypoint.sh"]
