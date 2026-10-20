#!/usr/bin/env python3
"""Migration: class_sessions.instructor_id becomes nullable.

Instructors are not yet assigned on the academy timetable, but dated class
sessions must exist for students to see their schedule. Rebuilds the table
from its live sqlite_master definition (preserving indexes) with the single
column relaxed. Idempotent — skips if already nullable.

Usage: python3 scripts/migrate_sessions_instructor.py <path-to.db>
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "../_local-preview/preview.db"


def main():
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()

    cols = list(cur.execute("PRAGMA table_info(class_sessions)"))
    ins = [c for c in cols if c[1] == "instructor_id"]
    if not ins:
        raise SystemExit("FATAL: class_sessions.instructor_id not found")
    if ins[0][3] == 0:
        print("class_sessions.instructor_id already nullable — nothing to do")
        con.close()
        return

    create_sql = cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='class_sessions'"
    ).fetchone()[0]
    indexes = [r[0] for r in cur.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='class_sessions' AND sql IS NOT NULL"
    )]

    tmp = "class_sessions_mig"
    new_sql = create_sql.replace(
        "CREATE TABLE class_sessions", f"CREATE TABLE {tmp}"
    ).replace(
        "instructor_id UUID NOT NULL", "instructor_id UUID"
    )
    if new_sql == create_sql or tmp not in new_sql:
        raise SystemExit("FATAL: could not rewrite CREATE statement for migration")
    cur.execute("PRAGMA foreign_keys=OFF")
    cur.execute("BEGIN")
    try:
        cur.execute(f"DROP TABLE IF EXISTS {tmp}")
        cur.execute(new_sql)
        # copy columns (same names in both tables)
        col_list = ", ".join(c[1] for c in cols)
        cur.execute(f"INSERT INTO {tmp} ({col_list}) SELECT {col_list} FROM class_sessions")
        cur.execute("DROP TABLE class_sessions")
        cur.execute(f"ALTER TABLE {tmp} RENAME TO class_sessions")
        for idx in indexes:
            cur.execute(idx)
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    finally:
        cur.execute("PRAGMA foreign_keys=ON")

    chk = [c for c in cur.execute("PRAGMA table_info(class_sessions)") if c[1] == "instructor_id"][0]
    print(f"class_sessions.instructor_id NOT NULL: {chk[3]} (0 = nullable) ✓")
    print(f"indexes restored: {len(indexes)}")
    con.close()
    print("MIGRATION OK")


if __name__ == "__main__":
    main()
