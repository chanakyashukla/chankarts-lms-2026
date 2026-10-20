#!/usr/bin/env python3
"""Additive migration: support messaging + achievements tables.

Creates (IF NOT EXISTS):
  support_requests, support_replies, support_attachments, achievements
No existing table or row is modified. Idempotent.

Usage: python3 scripts/migrate_support_achievements.py <path-to.db>
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "../_local-preview/preview.db"

DDL = [
    """
    CREATE TABLE IF NOT EXISTS support_requests (
        id CHAR(32) PRIMARY KEY,
        sender_user_id CHAR(32) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        sender_role VARCHAR(20) NOT NULL,
        subject VARCHAR(200) NOT NULL,
        message TEXT NOT NULL,
        related_student_id CHAR(32) REFERENCES students(id) ON DELETE SET NULL,
        related_enrollment_id CHAR(32) REFERENCES enrollments(id) ON DELETE SET NULL,
        related_session_id CHAR(32) REFERENCES class_sessions(id) ON DELETE SET NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'open',
        resolved_at DATETIME,
        resolved_by CHAR(32) REFERENCES users(id) ON DELETE SET NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_support_requests_sender ON support_requests (sender_user_id)",
    "CREATE INDEX IF NOT EXISTS ix_support_requests_status ON support_requests (status)",
    """
    CREATE TABLE IF NOT EXISTS support_replies (
        id CHAR(32) PRIMARY KEY,
        request_id CHAR(32) NOT NULL REFERENCES support_requests(id) ON DELETE CASCADE,
        author_user_id CHAR(32) REFERENCES users(id) ON DELETE SET NULL,
        author_role VARCHAR(20) NOT NULL,
        body TEXT NOT NULL,
        created_at DATETIME NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_support_replies_request ON support_replies (request_id)",
    """
    CREATE TABLE IF NOT EXISTS support_attachments (
        id CHAR(32) PRIMARY KEY,
        request_id CHAR(32) NOT NULL REFERENCES support_requests(id) ON DELETE CASCADE,
        reply_id CHAR(32) REFERENCES support_replies(id) ON DELETE CASCADE,
        uploaded_by CHAR(32) REFERENCES users(id) ON DELETE SET NULL,
        filename VARCHAR(255) NOT NULL,
        stored_name VARCHAR(80) NOT NULL UNIQUE,
        content_type VARCHAR(120) NOT NULL,
        size_bytes INTEGER,
        created_at DATETIME NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS achievements (
        id CHAR(32) PRIMARY KEY,
        student_id CHAR(32) NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        title VARCHAR(200) NOT NULL,
        category VARCHAR(40) NOT NULL DEFAULT 'award',
        awarding_body VARCHAR(120),
        programme_id VARCHAR(50),
        grade_level VARCHAR(40),
        result VARCHAR(80),
        achieved_on DATE,
        description TEXT,
        cert_stored_name VARCHAR(80),
        cert_filename VARCHAR(255),
        cert_content_type VARCHAR(120),
        is_verified BOOLEAN NOT NULL DEFAULT 0,
        is_archived BOOLEAN NOT NULL DEFAULT 0,
        created_by CHAR(32) REFERENCES users(id) ON DELETE SET NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_achievements_student ON achievements (student_id)",
]


def main():
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()
    for stmt in DDL:
        cur.execute(stmt)
    for t in ("support_requests", "support_replies", "support_attachments", "achievements"):
        n = list(cur.execute(f"SELECT COUNT(*) FROM {t}"))[0][0]
        print(f"{t}: ensured ({n} rows)")
    con.close()
    print("MIGRATION OK")


if __name__ == "__main__":
    main()
