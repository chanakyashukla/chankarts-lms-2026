"""Idempotent import of the pre-enrolled student dataset into production.

Source of truth (genuine, pre-browser-test snapshot):
    ~/Documents/ChankArts LMS/_local-preview/backups/preview-before-fee-ledger-20261017-235506.db

Scope
-----
* The 16 pre-enrolled students + their user accounts (credentials preserved
  verbatim — nothing is fabricated), instructors + parent logins REQUIRED by
  foreign keys of those students, and student-owned academic records
  (enrolments, schedules, sessions, attendance placeholders, syllabus links,
  assignments, achievements, exams, milestones, reports, notifications, …).
* EXCLUDED (never imported): browser-test financial transactions, invoices,
  payments, fee records, ledgers, exam fees, debug/demo charges, audit rows,
  support tickets, shared study material catalogue, sequence counters,
  platform admins, and any out-of-scope catalogue state.

Schema mapping: only columns present in BOTH source and production are
inserted; production-only columns get model/DB defaults; source-only columns
are ignored and reported.  Attribution columns (created_by / *_user_id)
whose value points at a user that is not imported are nulled (or mapped to
the current production admin when the column is NOT NULL).

Idempotency: primary-key inserts use ON CONFLICT DO NOTHING and business
keys (users.username, students.cma_registration_id) are skipped when they
already exist — rerunning never duplicates a student, account, enrolment or
class session.

Usage:
    python scripts/import_preview_students.py --dry-run
    python scripts/import_preview_students.py --apply
"""
import argparse
import asyncio
import hashlib
import os
import re
import sqlite3
import sys
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import MetaData, Table, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import create_async_engine

DEFAULT_SOURCE = str(
    Path.home()
    / "Documents" / "ChankArts LMS" / "_local-preview" / "backups"
    / "preview-before-fee-ledger-20261017-235506.db"
)

# financial / demo / out-of-scope tables that must never be imported
FINANCIAL_TABLES = {
    "invoices", "payments", "payment_orders", "payment_events",
    "payment_allocations", "receipts", "fee_records", "credit_ledger",
    "exam_fees", "fee_packages",
}
OUT_OF_SCOPE_TABLES = {
    "audit_events", "admins", "support_requests", "support_replies",
    "resource_recommendations", "study_materials", "sequence_counters",
    "password_history",
}

# ordered import plan: table -> selector(rows, scope) -> bool
# (children after parents; FK closure included)
def _in(val, s):
    return val is not None and val in s


def build_scope(src: dict[str, list[dict]]) -> dict:
    students = src.get("students", [])
    roster = {r["id"] for r in students}
    users_tbl = src.get("users", [])
    student_users = {r["user_id"] for r in students if r.get("user_id")}
    instructors = src.get("instructors", [])
    instructor_users = {r["user_id"] for r in instructors if r.get("user_id")}
    ga = [r for r in src.get("guardian_accounts", []) if _in(r.get("student_id"), roster)]
    parent_users = {r["user_id"] for r in ga if r.get("user_id")}
    user_set = student_users | instructor_users | parent_users
    enrollments = {r["id"] for r in src.get("enrollments", []) if _in(r.get("student_id"), roster)}
    sessions = {r["id"] for r in src.get("class_sessions", [])
                if _in(r.get("student_id"), roster) or _in(r.get("enrollment_id"), enrollments)}
    assignments = {r["id"] for r in src.get("assignments", [])
                   if _in(r.get("student_id"), roster) or _in(r.get("enrollment_id"), enrollments)}
    exams = {r["id"] for r in src.get("exams", [])
             if _in(r.get("student_id"), roster) or _in(r.get("enrollment_id"), enrollments)}
    ssa = [r for r in src.get("student_syllabus_assignments", []) if _in(r.get("student_id"), roster)]
    syllabi = {r.get("syllabus_id") for r in ssa if r.get("syllabus_id")}
    return {
        "roster": roster, "users": user_set, "student_users": student_users,
        "instructor_users": instructor_users, "parent_users": parent_users,
        "instructors": {r["id"] for r in instructors if r.get("user_id") in instructor_users},
        "enrollments": enrollments, "sessions": sessions,
        "assignments": assignments, "exams": exams,
        "syllabi": {s for s in syllabi if s},
        "user_ids_src": {r["id"] for r in users_tbl},
    }


def select_scope(table: str, rows: list[dict], sc: dict) -> list[dict]:
    roster, enr, sess = sc["roster"], sc["enrollments"], sc["sessions"]
    asg, exams, users = sc["assignments"], sc["exams"], sc["users"]

    def has_student(r):
        return _in(r.get("student_id"), roster) or _in(r.get("enrollment_id"), enr)

    if table == "users":
        return [r for r in rows if r.get("id") in users]
    if table == "instructors":
        return [r for r in rows if r.get("id") in sc["instructors"]]
    if table == "students":
        return [r for r in rows if r.get("id") in roster]
    if table in ("guardians", "guardian_accounts"):
        return [r for r in rows if _in(r.get("student_id"), roster)]
    if table == "enrollments":
        return [r for r in rows if r.get("id") in enr]
    if table == "class_schedules":
        return [r for r in rows if _in(r.get("enrollment_id"), enr)]
    if table == "class_sessions":
        return [r for r in rows if r.get("id") in sess]
    if table == "session_status_history":
        return [r for r in rows if _in(r.get("session_id"), sess)]
    if table == "syllabi":
        return [r for r in rows if r.get("id") in sc["syllabi"]]
    if table == "syllabus_items":
        return [r for r in rows if _in(r.get("syllabus_id"), sc["syllabi"])]
    if table == "assignments":
        return [r for r in rows if r.get("id") in asg]
    if table == "assignment_files":
        return [r for r in rows if _in(r.get("assignment_id"), asg)]
    if table == "submissions":
        return [r for r in rows
                if _in(r.get("student_id"), roster) or _in(r.get("assignment_id"), asg)
                or _in(r.get("enrollment_id"), enr)]
    if table == "exams":
        return [r for r in rows if r.get("id") in exams]
    if table == "exam_items":
        return [r for r in rows if _in(r.get("exam_id"), exams)]
    if table == "notifications":
        return [r for r in rows if _in(r.get("user_id"), users)]
    if table in ("pin_reset_requests", "email_verification_tokens"):
        return [r for r in rows if _in(r.get("user_id"), users)]
    if table == "registration_requests":
        return [r for r in rows if _in(r.get("student_id"), roster)]
    if table in ("attendance", "progress", "milestones", "monthly_reports",
                 "student_syllabus_assignments", "student_syllabus_progress",
                 "student_instruments", "student_remarks", "achievements",
                 "material_assignments", "resource_visibility_targets"):
        return [r for r in rows if has_student(r)]
    return []


IMPORT_ORDER = [
    "users", "instructors", "students", "guardians", "guardian_accounts",
    "syllabi", "syllabus_items", "enrollments", "class_schedules",
    "class_sessions", "session_status_history", "attendance", "progress",
    "milestones", "monthly_reports", "student_syllabus_assignments",
    "student_syllabus_progress", "student_instruments", "student_remarks",
    "achievements", "assignments", "assignment_files", "submissions",
    "exams", "exam_items", "material_assignments",
    "resource_visibility_targets", "notifications", "pin_reset_requests",
    "email_verification_tokens", "registration_requests",
]

ATTRIB_RE = re.compile(r"(_by|_user_id)$")


def load_source(path: str) -> dict[str, list[dict]]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    names = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    out = {}
    for t in names:
        out[t] = [dict(r) for r in con.execute(f'SELECT * FROM "{t}"')]
    con.close()
    return out


async def prod_meta(engine) -> tuple[dict, dict, set]:
    async with engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema='public'"))).all()
        meta: dict[str, dict[str, dict]] = {}
        for t, c, dt, nul, dflt in rows:
            meta.setdefault(t, {})[c] = {"type": dt, "nullable": nul == "YES", "default": dflt}
        tables = {r[0] for r in (await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'"))).all()}
        admin = (await conn.execute(text(
            "SELECT id FROM users WHERE role='ADMIN' ORDER BY created_at LIMIT 1"))).scalar()
    return meta, tables, set()


def coerce(value, colinfo: dict, model_col=None):
    if value is None:
        if not colinfo["nullable"] and colinfo["default"] is None:
            if model_col is not None and model_col.default is not None:
                arg = model_col.default.arg
                return arg() if callable(arg) else arg
            return None  # will fail → reported per row
        return None
    dt = colinfo["type"]
    if dt == "uuid":
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    if dt.startswith("timestamp"):
        return datetime.fromisoformat(str(value).replace("T", " ").split("+")[0].strip())
    if dt == "date":
        return date.fromisoformat(str(value)[:10])
    if dt == "time":
        return time.fromisoformat(str(value))
    if dt == "boolean":
        return bool(int(value)) if not isinstance(value, bool) else value
    if dt in ("numeric", "real", "double precision"):
        return Decimal(str(value))
    if dt in ("integer", "bigint", "smallint"):
        return int(value)
    if dt in ("json", "jsonb"):
        import json as _json
        return _json.loads(value) if isinstance(value, str) else value
    return value


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--apply", action="store_true", help="actually import (default: dry-run)")
    ap.add_argument("--dry-run", action="store_true", help="explicit no-op: report only (default)")
    ap.add_argument("--report", default="", help="write report to this path as well")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    mode = "APPLY" if args.apply else "DRY RUN"
    src_path = Path(args.source)
    if not src_path.exists():
        raise SystemExit(f"source not found: {src_path}")
    src = load_source(str(src_path))
    src_sha = hashlib.sha256(src_path.read_bytes()).hexdigest()[:16]
    sc = build_scope(src)

    engine = create_async_engine(url, pool_pre_ping=True)
    meta, prod_tables, _ = await prod_meta(engine)

    from app.database import Base  # model defaults for production-only columns
    import app.api.v1.router  # noqa: F401  (import full model graph)

    lines: list[str] = []
    def emit(s: str = ""):
        print(s)
        lines.append(s)

    emit(f"=== {mode}: pre-enrolled students → production ===")
    emit(f"source: {src_path}")
    emit(f"source sha256: {src_sha}")
    emit()

    # ---------- roster comparison ----------
    prod_reg = set()
    prod_user = set()
    async with engine.connect() as conn:
        for r in (await conn.execute(text("SELECT cma_registration_id FROM students"))).all():
            prod_reg.add(r[0])
        for r in (await conn.execute(text("SELECT username FROM users"))).all():
            prod_user.add(r[0])
    src_roster = src.get("students", [])
    src_regs = {r["cma_registration_id"]: r for r in src_roster}
    present = [k for k in src_regs if k in prod_reg]
    missing = [k for k in src_regs if k not in prod_reg]
    emit(f"ROSTER: source students={len(src_roster)} | already in production={len(present)} "
         f"| missing={len(missing)} | registration-ID collisions={len(present)}")
    for k in present:
        emit(f"  NOTE: source reg {k} already exists in production (kept as-is; "
             f"source row skipped — verify whether the existing row is a test profile)")

    # ---------- per-table plan ----------
    emit()
    emit("TABLE PLAN (source rows → in-scope → to-insert | existing-pk | biz-key-skip | excluded):")
    plan: dict[str, dict] = {}
    total_insert = 0
    biz_rules = {"users": ("username", prod_user), "students": ("cma_registration_id", prod_reg)}
    for t in IMPORT_ORDER:
        if t not in meta:
            emit(f"  {t:30} MISSING in production schema — skipped")
            continue
        srows = src.get(t, [])
        rows = select_scope(t, srows, sc)
        pk_existing = 0
        biz_skip = 0
        to_insert = rows
        if rows:
            async with engine.connect() as conn:
                ids = [r.get("id") for r in rows if r.get("id")]
                if ids:
                    q = text(f'SELECT id FROM "{t}" WHERE id = ANY(:ids)')
                    try:
                        found = {r[0] for r in (await conn.execute(q, {"ids": ids})).all()}
                    except Exception:
                        found = set()
                    pk_existing = len(found)
                    to_insert = [r for r in rows if r.get("id") not in found]
            if t in biz_rules:
                col, existing = biz_rules[t]
                keep, skip = [], 0
                for r in to_insert:
                    if r.get(col) in existing:
                        skip += 1
                    else:
                        keep.append(r)
                to_insert, biz_skip = keep, skip
        plan[t] = {"source": len(srows), "scope": len(rows), "insert": to_insert,
                   "pk_existing": pk_existing, "biz_skip": biz_skip}
        total_insert += len(to_insert)
        emit(f"  {t:30} {len(srows):5} → {len(rows):5} → insert {len(to_insert):5} "
             f"| existed-pk {pk_existing} | dup-key skip {biz_skip}")
    for t in sorted(set(src) - set(IMPORT_ORDER)):
        if t in FINANCIAL_TABLES:
            note = "financial/demo — EXCLUDED by policy"
        elif t in OUT_OF_SCOPE_TABLES:
            note = "out of scope — EXCLUDED"
        else:
            note = "not in import plan — EXCLUDED"
        if src.get(t):
            emit(f"  [excluded] {t:26} {len(src[t]):5} rows ({note})")
    emit()

    # ---------- schema mapping ----------
    emit("SCHEMA MAPPING:")
    src_cols = {}
    con = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    for t in IMPORT_ORDER:
        if t not in src or t not in meta:
            continue
        src_cols[t] = [r[1] for r in con.execute(f'PRAGMA table_info("{t}")')]
    con.close()
    for t, cols in src_cols.items():
        prod_cols = set(meta[t])
        s_only = [c for c in cols if c not in prod_cols]
        p_only = sorted(prod_cols - set(cols))
        if s_only:
            emit(f"  {t}: source-only (ignored): {', '.join(s_only)}")
        if p_only:
            emit(f"  {t}: production-only (defaults applied): {', '.join(p_only)}")
    emit()

    # ---------- attribution ----------
    imported_user_ids = {r.get("id") for r in plan.get("users", {}).get("insert", [])}
    async with engine.connect() as conn:
        prod_uids = {r[0] for r in (await conn.execute(text("SELECT id FROM users"))).all()}
        admin_id = (await conn.execute(text(
            "SELECT id FROM users WHERE role='ADMIN' ORDER BY created_at LIMIT 1"))).scalar()
    allowed_users = imported_user_ids | prod_uids
    attrib_null = attrib_map = 0
    for t, blk in plan.items():
        for r in blk["insert"]:
            for c in list(r):
                if not ATTRIB_RE.search(c):
                    continue
                v = r.get(c)
                if v is None or v in allowed_users:
                    continue
                if meta[t][c]["nullable"]:
                    r[c] = None
                    attrib_null += 1
                elif admin_id and c.endswith(("_by", "_user_id")):
                    r[c] = admin_id
                    attrib_map += 1
                else:
                    r[c] = None
    emit(f"ATTRIBUTION: {attrib_null} creator references to non-imported users → NULL; "
         f"{attrib_map} → mapped to current production admin")
    emit(f"TOTAL ROWS TO INSERT: {total_insert}")
    emit("IDEMPOTENT: yes (ON CONFLICT (id) DO NOTHING + username/registration-ID skip)")
    emit()

    if not args.apply:
        emit("DRY RUN only — nothing was written.")
        emit("Next: python scripts/import_preview_students.py --apply")
    else:
        # ---------------- APPLY ----------------
        md = MetaData()
        inserted_counts: dict[str, int] = {}
        failures: list[str] = []
        async with engine.begin() as conn:
            for t in IMPORT_ORDER:
                blk = plan.get(t)
                if not blk or not blk["insert"]:
                    continue
                table = Table(t, md, autoload_with=conn)
                cols_meta = meta[t]
                for r in blk["insert"]:
                    vals = {}
                    for c, v in r.items():
                        if c not in cols_meta:
                            continue
                        mcol = Base.metadata.tables.get(t)
                        mcol = mcol.c.get(c) if mcol is not None else None
                        vals[c] = coerce(v, cols_meta[c], mcol)
                    stmt = pg_insert(table).values(**vals).on_conflict_do_nothing(index_elements=["id"])
                    try:
                        res = await conn.execute(stmt)
                        inserted_counts[t] = inserted_counts.get(t, 0) + (res.rowcount or 0)
                    except Exception as e:  # noqa: BLE001 — record + continue (rerunnable)
                        failures.append(f"{t} id={r.get('id')}: {type(e).__name__}: {str(e)[:160]}")
        emit("APPLY RESULTS (rows actually inserted):")
        for t in IMPORT_ORDER:
            if inserted_counts.get(t):
                emit(f"  {t:30} +{inserted_counts[t]}")
        if failures:
            emit(f"FAILURES ({len(failures)}):")
            for f in failures[:40]:
                emit("  " + f)
        # post-verify
        async with engine.connect() as conn:
            n_stu = (await conn.execute(text("SELECT COUNT(*) FROM students"))).scalar()
            n_user = (await conn.execute(text("SELECT COUNT(*) FROM users WHERE role='STUDENT'"))).scalar()
            n_enr = (await conn.execute(text("SELECT COUNT(*) FROM enrollments"))).scalar()
            n_sch = (await conn.execute(text("SELECT COUNT(*) FROM class_schedules"))).scalar()
            n_ses = (await conn.execute(text("SELECT COUNT(*) FROM class_sessions"))).scalar()
            still_missing = (await conn.execute(text(
                "SELECT COUNT(*) FROM students WHERE cma_registration_id = ANY(:regs)"
            ), {"regs": list(src_regs)})).scalar()
        emit()
        emit("POST-APPLY VERIFY:")
        emit(f"  students={n_stu} (roster covered {still_missing}/{len(src_regs)}) "
             f"student-users={n_user} enrollments={n_enr} schedules={n_sch} sessions={n_ses}")
        emit("Rerun this script with --dry-run: 'TOTAL ROWS TO INSERT' must be 0.")
        if failures:
            raise SystemExit(3)

    await engine.dispose()
    if args.report:
        Path(args.report).expanduser().write_text("\n".join(lines) + "\n")
        print(f"report written: {args.report}")


if __name__ == "__main__":
    asyncio.run(main())
