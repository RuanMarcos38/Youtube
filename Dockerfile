# syntax=docker/dockerfile:1.7

FROM node:22-bookworm-slim AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
ARG BACKEND_INTERNAL_URL=http://127.0.0.1:8000
ENV BACKEND_INTERNAL_URL=${BACKEND_INTERNAL_URL} \
    NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:22-bookworm-slim AS pot-provider-builder
WORKDIR /build/pot-provider
ADD https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/1.3.1.tar.gz /tmp/bgutil-ytdlp-pot-provider.tar.gz
RUN tar -xzf /tmp/bgutil-ytdlp-pot-provider.tar.gz --strip-components=2 \
    bgutil-ytdlp-pot-provider-1.3.1/server \
    && npm ci --no-audit --no-fund \
    && npx tsc \
    && npm prune --omit=dev --no-audit --no-fund

FROM node:22-bookworm-slim AS runtime
ENV DEBIAN_FRONTEND=noninteractive \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    SQLITE_PATH=/app/data/app.db \
    YTDLP_POT_PROVIDER_URL=http://127.0.0.1:4416 \
    DISPLAY=:99 \
    CHROME_BIN=/usr/bin/chromium

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip ffmpeg ca-certificates fonts-dejavu-core supervisor libgomp1 \
    chromium xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/venv
WORKDIR /app/backend
COPY backend/requirements.txt ./requirements.txt
RUN /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt \
    && test -x /usr/bin/chromium \
    && /opt/venv/bin/python -c "import importlib.util; assert importlib.util.find_spec('yt_dlp_plugins.extractor.getpot_wpc')"
COPY backend/ /app/backend/

COPY --from=pot-provider-builder /build/pot-provider /app/pot-provider
COPY --from=frontend-builder /build/frontend/.next/standalone /app/frontend
COPY --from=frontend-builder /build/frontend/.next/static /app/frontend/.next/static
COPY --from=frontend-builder /build/frontend/public /app/frontend/public
COPY deploy/supervisord.conf /etc/supervisor/conf.d/shortsflow.conf

RUN mkdir -p /app/data /var/log/supervisor
EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=35s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/supervisord.conf"]
