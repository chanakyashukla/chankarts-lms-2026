#!/usr/bin/env python3
"""Additive migration: student-specific syllabus assignments.

Creates `student_syllabus_assignments` and backfills one ACTIVE assignment
for every (student, enrolment, syllabus) that already has progress rows —
those syllabi are demonstrably part of that student's plan. Syllabi with no
progress stay unassigned and remain admin-only (nothing new becomes visible).

Idempotent: re-running only fills gaps.

Usage: python3 scripts/migrate_syllabus_assignments.py <path-to.db>
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "../_local-preview/preview.db"

DDL = """
CREATE TABLE IF NOT EXISTS student_syllabus_assignments (
    id CHAR(32) PRIMARY KEY,
    student_id CHAR(32) NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    enrollment_id CHAR(32) NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
    syllabus_id CHAR(32) NOT NULL REFERENCES syllabi(id) ON DELETE CASCADE,
    instructor_id CHAR(32) REFERENCES instructors(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    assigned_by CHAR(32) REFERENCES users(id) ON DELETE SET NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_syllabus_assignment UNIQUE (student_id, syllabus_id, enrollment_id)
)
"""


def main():
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()

    cur.execute(DDL)
    print("student_syllabus_assignments: table ensured")

    # backfill from existing per-student progress rows (source of truth for
    # "this syllabus is already part of this student's plan")
    cur.execute("""
        INSERT OR IGNORE INTO student_syllabus_assignments
            (id, student_id, enrollment_id, syllabus_id, instructor_id,
             status, assigned_by, created_at, updated_at)
        SELECT
            lower(hex(randomblob(16))),
            p.student_id,
            p.enrollment_id,
            p.syllabus_id,
            e.instructor_id,
            'active',
            NULL,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM (SELECT DISTINCT student_id, enrollment_id, syllabus_id
              FROM student_syllabus_progress) p
        LEFT JOIN enrollments e ON e.id = p.enrollment_id
        WHERE NOT EXISTS (
            SELECT 1 FROM student_syllabus_assignments a
            WHERE a.student_id = p.student_id
              AND a.syllabus_id = p.syllabus_id
              AND a.enrollment_id = p.enrollment_id
        )
    """)
    print(f"student_syllabus_assignments: backfilled {cur.rowcount} assignment(s) from progress rows")

    total = list(cur.execute("SELECT COUNT(*) FROM student_syllabus_assignments"))[0][0]
    print(f"student_syllabus_assignments: {total} total")
    con.close()
    print("MIGRATION OK")


if __name__ == "__main__":
    main()
