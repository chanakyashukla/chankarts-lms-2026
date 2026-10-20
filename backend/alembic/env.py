import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base
import app.models  # noqa: F401  — register all tables on Base.metadata
import os

from app.config import get_settings

config = context.config
settings = get_settings()
# Migrations use MIGRATIONS_DATABASE_URL when provided (the DIRECT Neon
# endpoint — Neon's guidance: schema migrations must not go through the
# pooled/transaction-mode endpoint). Application traffic keeps DATABASE_URL
# (pooled) untouched.
_migrations_url = os.environ.get("MIGRATIONS_DATABASE_URL") or settings.MIGRATIONS_DATABASE_URL or settings.DATABASE_URL
# configparser treats % as interpolation — escape it for safe URL transport
config.set_main_option("sqlalchemy.url", _migrations_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with the installed async driver (asyncpg/aiosqlite).

    A sync engine cannot drive an async driver (it fails with
    MissingGreenlet), so migrations run through the async engine and
    SQLAlchemy's run_sync bridge — the pattern from Alembic's own
    async cookbook. Works with both DATABASE_URL and the optional
    MIGRATIONS_DATABASE_URL.
    """
    url = config.get_main_option("sqlalchemy.url")

    def do_run_migrations(connection):
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()

    async def run_async_migrations():
        connectable = create_async_engine(url, poolclass=pool.NullPool)
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
        await connectable.dispose()

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
