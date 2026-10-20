from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from app.config import get_settings
from app.api.v1.router import api_router
from app import static_frontend

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run migrations on startup (safe for non-Docker deploys)
    try:
        import os as _os
        import subprocess
        import sys
        # Migrations may use MIGRATIONS_DATABASE_URL (direct endpoint) while
        # the application itself always connects via the pooled DATABASE_URL.
        _env = dict(_os.environ)
        if settings.MIGRATIONS_DATABASE_URL:
            _env["MIGRATIONS_DATABASE_URL"] = settings.MIGRATIONS_DATABASE_URL
        _run = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(__import__("pathlib").Path(__file__).parent.parent),
            check=False,
            capture_output=True,
            env=_env,
        )
        if _run.returncode == 0:
            print("Database migrations applied successfully")
        else:
            detail = (_run.stderr or b"").decode(errors="replace").strip()[-500:]
            # Non-fatal: the additive schema bootstrap below still aligns the
            # database with the models, but the real failure is now visible.
            print(f"Migration warning (non-fatal): alembic exit {_run.returncode}: {detail}")
    except Exception as e:
        print(f"Migration warning (non-fatal): {e}")

    # Additive schema bootstrap: brings a fresh PostgreSQL (or SQLite) database
    # up to the models after the migrations run (never destructive).
    try:
        from app.database import engine as _engine
        from app.db_bootstrap import sync_schema
        for line in await sync_schema(_engine):
            print(f"schema bootstrap: {line}")
    except Exception as e:
        print(f"Schema bootstrap warning (non-fatal): {e}")

    # Production safety notice
    if not settings.DEBUG and settings.SECRET_KEY.startswith("your-secret-key"):
        print("WARNING: SECRET_KEY is still the default value — set a strong SECRET_KEY in production")

    # Seed admin user from env vars
    try:
        from app.database import AsyncSessionLocal
        from app.core.seed import seed_admin
        async with AsyncSessionLocal() as session:
            await seed_admin(session)
            await session.commit()
    except Exception as e:
        print(f"Admin seed warning (non-fatal): {e}")

    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="ChankArts Music Academy Learning Management System API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS configuration.
# Defaults cover the production domains and local development. Override or
# extend at deployment time with ALLOWED_ORIGINS="https://a.example,https://b.example"
_default_origins = [
    "https://chankarts.com",
    "https://www.chankarts.com",
    "https://academy.chankarts.com",
    "https://chanakyashukla.github.io",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
]
_env_origins = [o.strip() for o in (getattr(settings, "ALLOWED_ORIGINS", "") or "").split(",") if o.strip()]
ALLOWED_ORIGINS = list(dict.fromkeys(_env_origins + _default_origins)) if _env_origins else _default_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Conservative security headers + no-store on authenticated payloads."""
    import logging

    try:
        response = await call_next(request)
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger("chankarts.errors").exception(
            "Unhandled error on %s %s", request.method, request.url.path
        )
        if settings.DEBUG:
            raise
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if settings.DEBUG:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self' https: http://localhost:* http://127.0.0.1:* data: blob: 'unsafe-inline' 'unsafe-eval'",
        )
    return response


app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "active"
    }


# Same-origin frontend (static files + SPA fallback) under /academy/*
app.include_router(static_frontend.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
