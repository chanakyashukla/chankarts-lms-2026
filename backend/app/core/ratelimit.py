"""
Minimal in-memory sliding-window rate limiter for auth-sensitive endpoints.

Single-process only (fine for the current single-worker deployment). Swap for
a Redis-backed limiter before horizontal scaling.
"""
import time
from collections import defaultdict, deque
from fastapi import HTTPException, Request, status

_buckets: dict[str, deque] = defaultdict(deque)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(bucket: str, key: str, max_attempts: int, window_seconds: int) -> None:
    """Raise 429 when `max_attempts` is exceeded inside the sliding window."""
    from app.config import get_settings

    if not get_settings().RATE_LIMIT_ENABLED:
        return

    now = time.monotonic()
    q = _buckets[f"{bucket}:{key}"]
    while q and now - q[0] > window_seconds:
        q.popleft()
    if len(q) >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait and try again.",
        )
    q.append(now)


def reset_rate_limits() -> None:
    _buckets.clear()
