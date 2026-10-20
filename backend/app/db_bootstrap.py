"""
Engine-agnostic schema bootstrap.

On deployment the database may be a FRESH PostgreSQL instance where only the
Alembic migrations have run. Several tables and columns introduced during
development were applied through additive local scripts, not migrations.
Rather than maintaining a second migration chain, this bootstrap brings the
live schema up to the models in a purely ADDITIVE way:

1. `create_all(checkfirst=True)` — creates any table the models declare that
   does not exist yet (safe on both PostgreSQL and SQLite).
2. Column sync — adds any column the models declare that a table is missing
   (ALTER TABLE ... ADD COLUMN, engine-compiled types).
3. Nullable relaxations — a few columns changed from NOT NULL to nullable
   during development (PostgreSQL supports DROP NOT NULL; SQLite tables are
   already relaxed or created correctly from the models).

Nothing is dropped, truncated or rewritten. Idempotent: running it again is a
no-op. Alembic remains the source for the original schema history.
"""
from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn

from app.database import Base

# columns that were relaxed from NOT NULL -> NULL during development
NULLABLE_RELAXATIONS = (
    ("users", "email"),
    ("users", "username"),
    ("students", "date_of_birth"),
    ("class_sessions", "instructor_id"),
)


def _column_ddl(conn, col) -> str:
    try:
        return str(CreateColumn(col).compile(dialect=conn.dialect))
    except Exception:
        # Enum and exotic types compile to dialect-specific names; fall back
        # to a plain string so the ADD COLUMN always succeeds.
        return f"{col.name} VARCHAR(80)"


def _sync_connection(conn) -> list:
    log = []
    insp = inspect(conn)

    # 2) additive column sync
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name in existing:
                continue
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {_column_ddl(conn, col)}"
            try:
                conn.execute(text(ddl))
                log.append(f"column added: {table.name}.{col.name}")
            except Exception as exc:  # never fatal — report and continue
                log.append(f"column SKIP {table.name}.{col.name}: {exc}")

    # 3) nullable relaxations (PostgreSQL only; SQLite cannot drop NOT NULL,
    # but local SQLite databases were already relaxed by additive scripts and
    # fresh ones are created correctly from the models)
    if conn.dialect.name == "postgresql":
        for table_name, column_name in NULLABLE_RELAXATIONS:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table_name} ALTER COLUMN {column_name} DROP NOT NULL"
                ))
                log.append(f"nullable relaxed: {table_name}.{column_name}")
            except Exception as exc:
                log.append(f"nullable SKIP {table_name}.{column_name}: {exc}")

    return log


async def sync_schema(engine) -> list:
    """Bring the live database up to the models. Additive and idempotent."""
    log = []
    async with engine.begin() as conn:
        # 1) missing tables (any dialect)
        await conn.run_sync(Base.metadata.create_all)
        log.append("create_all done")
        log.extend(await conn.run_sync(_sync_connection))
    return log
