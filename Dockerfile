FROM python:3.12-slim

WORKDIR /app

# System dependencies: PostgreSQL driver build + FUSE for durable R2 uploads
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    ca-certificates \
    fuse \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# tigrisfs: S3-compatible FUSE adapter used to mount the R2 uploads bucket
# (see docker-entrypoint.sh). Harmless when R2 credentials are not provided.
ARG TIGRISFS_VERSION=1.2.1
RUN ARCH=$(uname -m) && \
    case "$ARCH" in x86_64) ARCH=amd64 ;; aarch64) ARCH=arm64 ;; esac && \
    curl -fL "https://github.com/tigrisdata/tigrisfs/releases/download/v${TIGRISFS_VERSION}/tigrisfs_${TIGRISFS_VERSION}_linux_${ARCH}.tar.gz" -o /tmp/tigrisfs.tar.gz && \
    tar -xzf /tmp/tigrisfs.tar.gz -C /usr/local/bin/ && \
    rm /tmp/tigrisfs.tar.gz && \
    chmod +x /usr/local/bin/tigrisfs

# Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (backend/ is the app root inside the image)
COPY backend/ .
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

# Entrypoint mounts durable uploads (optional) and starts uvicorn;
# migrations run exactly once at application startup (app/main.py).
ENTRYPOINT ["/app/docker-entrypoint.sh"]
