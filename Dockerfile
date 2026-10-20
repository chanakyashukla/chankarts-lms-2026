FROM python:3.12-slim

WORKDIR /app

# System dependencies for PostgreSQL driver builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (backend/ is the app root inside the image)
COPY backend/ .
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 8000

# Migrations + additive schema bootstrap run at startup (see app/main.py)
ENTRYPOINT ["/app/docker-entrypoint.sh"]
