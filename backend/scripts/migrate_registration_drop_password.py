#!/usr/bin/env python3
"""Additive-safe migration: remove the unused application password hash.

Applications (registration_requests) are enquiries only — no account
credentials were ever issued from this column. Rebuild the table without
`password_hash`, preserving every row and its history. Idempotent.

Usage: python3 scripts/migrate_registration_drop_password.py <path-to.db>
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "../_local-preview/preview.db"

OLD_COLS = [
    "id", "request_id", "full_name", "email", "mobile", "password_hash",
    "date_of_birth", "is_minor", "address", "guardian_name",
    "guardian_relationship", "guardian_email", "guardian_mobile",
    "selected_programmes", "status", "reviewed_by", "reviewed_at",
    "review_notes", "student_id", "created_at", "updated_at",
]


def main():
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()

    cols = [r[1] for r in cur.execute("PRAGMA table_info(registration_requests)")]
    if "password_hash" not in cols:
        print("registration_requests: password_hash already removed")
        con.close()
        print("MIGRATION OK (no-op)")
        return

    keep = [c for c in cols if c != "password_hash"]
    cur.execute("BEGIN")
    cur.execute("ALTER TABLE registration_requests RENAME TO _registration_requests_old")
    cur.execute("CREATE TABLE registration_requests AS SELECT "
                + ", ".join(keep) + " FROM _registration_requests_old")
    cur.execute("DROP TABLE _registration_requests_old")
    cur.execute("COMMIT")

    n = list(cur.execute("SELECT COUNT(*) FROM registration_requests"))[0][0]
    print(f"registration_requests: rebuilt without password_hash ({n} rows preserved)")
    con.close()
    print("MIGRATION OK")


if __name__ == "__main__":
    main()
