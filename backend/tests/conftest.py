"""
Shared pytest configuration.

Environment variables are set BEFORE any application import so that Settings
picks them up (and the app never touches a real database or email provider).
"""
import os

os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("EMAIL_TEST_MODE", "true")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("SEED_DEMO_DATA", "false")
