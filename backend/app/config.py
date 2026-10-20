from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/chankarts_academy"
    
    # JWT
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Application
    APP_NAME: str = "ChankArts Music Academy LMS"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    
    # Frontend URL (for email verification links)
    FRONTEND_URL: str = "https://chankarts.com"
    ALLOWED_ORIGINS: str = ""  # optional comma-separated extra CORS origins

    # Academy defaults
    TIMEZONE: str = "Asia/Kolkata"
    CURRENCY: str = "INR"

    # Email (Web3Forms)
    WEB3FORMS_ACCESS_KEY: str = ""
    EMAIL_TEST_MODE: bool = True
    ADMIN_EMAIL: str = "chankarts.official@gmail.com"
    FROM_NAME: str = "ChankArts Music Academy"

    # Payments (Razorpay) — server-side only, never exposed to the browser
    RAZORPAY_MODE: str = "disabled"          # disabled | test | live
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""
    RAZORPAY_CURRENCY: str = "INR"

    # File uploads (homework, study material)
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 15

    # Rate limiting (in-memory, per-process)
    RATE_LIMIT_ENABLED: bool = True
    AUTH_RATE_LIMIT_ATTEMPTS: int = 20
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 300
    REGISTRATION_RATE_LIMIT_ATTEMPTS: int = 5
    REGISTRATION_RATE_LIMIT_WINDOW_SECONDS: int = 3600

    # Seed Admin (set these env vars to auto-create an admin on first startup)
    SEED_ADMIN_EMAIL: str = ""
    SEED_ADMIN_USERNAME: str = ""
    SEED_ADMIN_PASSWORD: str = ""
    SEED_ADMIN_FIRST_NAME: str = "Admin"
    SEED_ADMIN_LAST_NAME: str = "User"

    # Development-only demo seed (never enable in production)
    SEED_DEMO_DATA: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
