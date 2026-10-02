FROM node:24.20.0-bookworm-slim AS web
WORKDIR /src/app
COPY app/package.json app/package-lock.json ./
RUN npm ci
COPY app/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    CREATIVEOS_DB_PATH=/data/creativeos.sqlite3 \
    CREATIVEOS_OUTPUT_ROOT=/data/output \
    CREATIVEOS_DIST_ROOT=/app/app/dist \
    CREATIVEOS_BIND_HOST=0.0.0.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /src/app/dist app/dist
EXPOSE 8000
CMD ["python", "-m", "creativeos_db.server"]
