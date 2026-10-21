"""Logical backup of EVERY production table to JSON + read-back verification.

Usage:
    DATABASE_URL=postgresql+asyncpg://... python scripts/backup_production.py \
        --out "/path/to/backups/prod-neon-YYYYmmdd-HHMMSS.json"

The backup is verified before the script reports success: each table is
re-read from the file and its row count compared with a live count taken
AFTER the dump (so drift is detected).  File mode is 0600.  No secrets are
printed (only table names, counts and the file's sha256).
"""
import argparse
import asyncio
import base64
import decimal
import hashlib
import json
import os
import sys
import uuid
from datetime import date, datetime, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def ser(v):
    if isinstance(v, (uuid.UUID,)):
        return str(v)
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return str(v)
    if isinstance(v, (bytes, memoryview)):
        return {"__bytes__": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, (dict, list)):
        return v
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    out = Path(args.out).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(url, pool_pre_ping=True)
    payload: dict = {"generated_at": datetime.utcnow().isoformat(), "tables": {}}
    async with engine.connect() as conn:
        tables = [r[0] for r in (await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        ))).all()]
        for t in tables:
            rows = (await conn.execute(text(f'SELECT * FROM "{t}"'))).mappings().all()
            cols = list(rows[0].keys()) if rows else [
                r[0] for r in (await conn.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
                ), {"t": t})).all()]
            payload["tables"][t] = {
                "columns": cols,
                "rows": [{k: ser(row[k]) for k in cols} for row in rows],
            }
        # live counts AFTER the dump (drift detection)
        live_counts = {t: (await conn.execute(text(f'SELECT COUNT(*) FROM "{t}"'))).scalar()
                       for t in tables}

    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=None, separators=(",", ":")))
    os.chmod(tmp, 0o600)
    tmp.replace(out)
    os.chmod(out, 0o600)

    # ---- verification: re-read file, compare counts with live DB ----
    check = json.loads(out.read_text())
    mismatches = []
    file_counts = {}
    for t, blk in check["tables"].items():
        file_counts[t] = len(blk["rows"])
        if file_counts[t] != live_counts.get(t):
            mismatches.append(f"{t}: file={file_counts[t]} live={live_counts.get(t)}")
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    total = sum(file_counts.values())
    print(f"backup file: {out}")
    print(f"tables: {len(file_counts)} | rows: {total} | sha256: {digest[:16]}…")
    if mismatches:
        print("VERIFICATION FAILED:")
        for m in mismatches:
            print("  " + m)
        raise SystemExit(2)
    print("VERIFICATION OK: every table's file row count matches the live database")

    for key in ("students", "users", "enrollments", "invoices", "fee_records"):
        print(f"  {key}: {file_counts.get(key, 0)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
