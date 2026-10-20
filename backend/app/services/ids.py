"""
Concurrency-safe sequential ID generation.

PostgreSQL: real sequences (atomic, safe under concurrent submissions).
SQLite (tests/dev): table-backed counter with an immediate transaction.

Formats:
  CMA Registration ID : CMA-YYYY-####   (students)
  Application ref     : REQ-YYYY-####   (registration requests)
  Invoice number      : CMA/INV/YYYY/MMMM
"""
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _dialect(db: AsyncSession) -> str:
    return db.get_bind().dialect.name


async def next_sequence_value(db: AsyncSession, sequence_name: str) -> int:
    """Return the next value for a named yearly sequence."""
    dialect = await _dialect(db)

    if dialect == "postgresql":
        await db.execute(text(f"CREATE SEQUENCE IF NOT EXISTS {sequence_name} START 1"))
        result = await db.execute(text(f"SELECT nextval('{sequence_name}')"))
        return int(result.scalar())

    # SQLite / others: counter table updated inside the caller's transaction
    await db.execute(text(
        "CREATE TABLE IF NOT EXISTS sequence_counters ("
        "name VARCHAR(80) PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0)"
    ))
    result = await db.execute(
        text("SELECT value FROM sequence_counters WHERE name = :name"), {"name": sequence_name}
    )
    current = result.scalar()
    if current is None:
        await db.execute(
            text("INSERT INTO sequence_counters (name, value) VALUES (:name, 1)"),
            {"name": sequence_name},
        )
        return 1
    new_value = int(current) + 1
    await db.execute(
        text("UPDATE sequence_counters SET value = :value WHERE name = :name"),
        {"value": new_value, "name": sequence_name},
    )
    return new_value


async def generate_request_id(db: AsyncSession, year: int | None = None) -> str:
    """REQ-YYYY-#### — sequential and concurrency-safe."""
    year = year or datetime.utcnow().year
    value = await next_sequence_value(db, f"req_seq_{year}")
    return f"REQ-{year}-{value:04d}"


class CMAIdService:
    """CMA-YYYY-#### student registration IDs."""

    @staticmethod
    async def generate_cma_id(db: AsyncSession, year: int | None = None) -> str:
        year = year or datetime.utcnow().year
        value = await next_sequence_value(db, f"cma_seq_{year}")
        return f"CMA-{year}-{value:04d}"

    @staticmethod
    def parse_cma_id(cma_id: str) -> tuple[int, int]:
        parts = cma_id.split("-")
        if len(parts) != 3 or parts[0] != "CMA":
            raise ValueError(f"Invalid CMA ID format: {cma_id}")
        return int(parts[1]), int(parts[2])


async def generate_invoice_number(db: AsyncSession, billing_month: str) -> str:
    """CMA/INV/YYYY/MMMM — sequential per year, uniqueness enforced by DB constraint."""
    year = int(billing_month.split("-")[0])
    value = await next_sequence_value(db, f"inv_seq_{year}")
    return f"CMA/INV/{year}/{value:04d}"
