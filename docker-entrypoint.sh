#!/bin/sh
set -e

# ---------------------------------------------------------------------------
# Durable uploads (optional): mount an R2 bucket at $UPLOAD_DIR using the
# tigrisfs FUSE adapter. When R2 credentials are absent (local development),
# uploads fall back to the container-local directory.
#
# Migrations are intentionally NOT run here: application startup
# (app/main.py) runs `alembic upgrade head` + the additive schema bootstrap
# exactly once. Running them in two places risks concurrent DDL on boot.
# ---------------------------------------------------------------------------
if [ -n "${R2_BUCKET_NAME:-}" ] && [ -n "${AWS_ACCESS_KEY_ID:-}" ]; then
    echo "Mounting R2 bucket '${R2_BUCKET_NAME}' for durable uploads..."
    MOUNT_DIR="${R2_MOUNT_DIR:-/mnt/r2}"
    mkdir -p "$MOUNT_DIR"
    /usr/local/bin/tigrisfs \
        --endpoint "https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com" \
        --region auto -f "$R2_BUCKET_NAME" "$MOUNT_DIR" &
    FUSE_PID=$!
    ATTEMPT=0
    until mountpoint -q "$MOUNT_DIR"; do
        if ! kill -0 "$FUSE_PID" 2>/dev/null; then
            echo "FUSE mount process exited before mounting — continuing with local uploads" >&2
            break
        fi
        ATTEMPT=$((ATTEMPT + 1))
        if [ "$ATTEMPT" -ge 20 ]; then
            echo "Timed out mounting R2 — continuing with local uploads" >&2
            break
        fi
        sleep 1
    done
    if mountpoint -q "$MOUNT_DIR"; then
        export UPLOAD_DIR="${UPLOAD_DIR:-$MOUNT_DIR/uploads}"
        mkdir -p "$UPLOAD_DIR"
        echo "Uploads directory: $UPLOAD_DIR (R2-backed, durable across container restarts)"
    else
        # PRODUCTION SAFETY: R2 was configured but did not mount. Continuing
        # would silently store uploads on ephemeral container-local disk.
        # Local development may opt into the fallback explicitly.
        if [ "${UPLOAD_FALLBACK_LOCAL:-false}" = "true" ]; then
            echo "WARNING: R2 mount failed — UPLOAD_FALLBACK_LOCAL=true, using container-local uploads (NOT durable)" >&2
        else
            echo "FATAL: R2 credentials are configured but the bucket could not be mounted." >&2
            echo "Refusing to start with ephemeral uploads. Fix the R2 credentials/bucket," >&2
            echo "or set UPLOAD_FALLBACK_LOCAL=true explicitly for local development." >&2
            exit 1
        fi
    fi
fi

echo "Starting server (migrations run at application startup)..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
