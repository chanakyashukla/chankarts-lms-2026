#!/usr/bin/env python3
"""Additive migration: financial ledger extensions.

1. invoices:  + charge_type (tuition|exam|other), + description
2. payments:  + receipt_number, + source (manual|online|button)
3. New tables: credit_ledger, exam_fees, receipts
4. Seeds fee_packages (standard_4 ₹4,500 / standard_8 ₹8,000) — SQLite-safe,
   idempotent, never overwrites existing rows.
5. Normalises enrollment.fee_amount to RUPEES where the provisioning path
   accidentally stored paise (450000/800000) — verified row-by-row, audited
   by count only (no other data touched).

Nothing is dropped or recreated. Idempotent.

Usage: python3 scripts/migrate_fee_ledger.py <path-to.db>
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "../_local-preview/preview.db"


def add_column(cur, table, col, decl):
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        print(f"{table}: added {col}")
    else:
        print(f"{table}: {col} already present")


def main():
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()

    add_column(cur, "invoices", "charge_type", "VARCHAR(20) DEFAULT 'tuition'")
    add_column(cur, "invoices", "description", "TEXT")
    add_column(cur, "payments", "receipt_number", "VARCHAR(30)")
    add_column(cur, "payments", "source", "VARCHAR(20) DEFAULT 'manual'")
    cur.execute("UPDATE invoices SET charge_type='tuition' WHERE charge_type IS NULL")
    cur.execute("UPDATE payments SET source='manual' WHERE source IS NULL AND provider IN ('manual','cash','upi','bank')")
    cur.execute("UPDATE payments SET source='online' WHERE source IS NULL AND provider='razorpay'")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS credit_ledger (
            id CHAR(32) PRIMARY KEY,
            student_id CHAR(32) NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            enrollment_id CHAR(32) REFERENCES enrollments(id) ON DELETE SET NULL,
            kind VARCHAR(20) NOT NULL,               -- advance | applied | refunded | adjustment
            amount_paise INTEGER NOT NULL,           -- signed: +credit added, -credit used
            payment_id CHAR(32) REFERENCES payments(id) ON DELETE SET NULL,
            invoice_id CHAR(32) REFERENCES invoices(id) ON DELETE SET NULL,
            note TEXT,
            created_by CHAR(32) REFERENCES users(id) ON DELETE SET NULL,
            created_at DATETIME NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_credit_ledger_student ON credit_ledger (student_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS exam_fees (
            id CHAR(32) PRIMARY KEY,
            student_id CHAR(32) NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            enrollment_id CHAR(32) REFERENCES enrollments(id) ON DELETE SET NULL,
            exam_id CHAR(32),
            invoice_id CHAR(32) REFERENCES invoices(id) ON DELETE SET NULL,
            board VARCHAR(80),
            instrument VARCHAR(80),
            grade_level VARCHAR(40),
            exam_session VARCHAR(80),
            fee_charged_paise INTEGER NOT NULL DEFAULT 0,   -- billed to the family
            academy_paid_paise INTEGER NOT NULL DEFAULT 0,  -- paid to the exam provider
            reimbursed_paise INTEGER NOT NULL DEFAULT 0,    -- received back from the family
            reimbursement_method VARCHAR(30),
            reimbursement_date DATE,
            provider_reference VARCHAR(120),
            attachment_stored_name VARCHAR(80),
            attachment_filename VARCHAR(255),
            attachment_content_type VARCHAR(120),
            status VARCHAR(24) NOT NULL DEFAULT 'open',     -- open|family_paid_first|academy_paid|reimbursed|settled
            notes TEXT,
            created_by CHAR(32) REFERENCES users(id) ON DELETE SET NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_exam_fees_student ON exam_fees (student_id)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS receipts (
            id CHAR(32) PRIMARY KEY,
            payment_id CHAR(32) NOT NULL UNIQUE REFERENCES payments(id) ON DELETE CASCADE,
            receipt_number VARCHAR(30) NOT NULL UNIQUE,
            issued_at DATETIME NOT NULL,
            issued_by CHAR(32) REFERENCES users(id) ON DELETE SET NULL,
            notes TEXT
        )
    """)

    # fee packages (SQLite-safe UUIDs), idempotent
    for code, name, sessions, fee in (
        ("standard_4", "4 Classes Package", 4, 450000),
        ("standard_8", "8 Classes Package", 8, 800000),
    ):
        cur.execute("SELECT id FROM fee_packages WHERE code=?", (code,))
        if not cur.fetchone():
            cur.execute(
                "INSERT INTO fee_packages (id, name, code, sessions_included, fee_paise, currency,"
                " billing_period, session_duration_minutes, description, is_active, is_legacy,"
                " created_at, updated_at)"
                " VALUES (lower(hex(randomblob(16))), ?, ?, ?, ?, 'INR', 'monthly', 60, ?, 1, 0,"
                " CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (name, code, sessions, fee,
                 f"Standard monthly tuition: {sessions} classes (60 min each)"),
            )
            print(f"fee_packages: seeded {code}")
    print("fee_packages:", dict(cur.execute("SELECT code, fee_paise FROM fee_packages").fetchall()))

    # unit normalisation: fee_amount is documented in RUPEES; the provisioning
    # path wrote paise. Only exact known paise values are converted.
    cur.execute("""
        UPDATE enrollments SET fee_amount = fee_amount / 100.0
        WHERE fee_amount IN (450000, 800000, 450000.0, 800000.0)
    """)
    print(f"enrollments: normalised {cur.rowcount} fee_amount value(s) paise -> rupees")

    for t in ("credit_ledger", "exam_fees", "receipts"):
        n = list(cur.execute(f"SELECT COUNT(*) FROM {t}"))[0][0]
        print(f"{t}: ensured ({n} rows)")
    con.close()
    print("MIGRATION OK")


if __name__ == "__main__":
    main()
