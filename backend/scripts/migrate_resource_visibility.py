#!/usr/bin/env python3
"""Additive migration: admin-controlled resource visibility.

1. Adds `visibility_scope` to study_materials and resource_recommendations.
2. Creates `resource_visibility_targets` (explicit per-student targeting).
3. Backfills a SAFE scope for existing rows — nothing becomes more visible:
     material with explicit assignments -> 'students'
     material with programme_id        -> 'programme'
     otherwise (already academy-wide)  -> 'all'
     recommendation with programme_id  -> 'programme'
     otherwise                         -> 'all'
Idempotent.

Usage: python3 scripts/migrate_resource_visibility.py <path-to.db>
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "../_local-preview/preview.db"


def main():
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()

    for table in ("study_materials", "resource_recommendations"):
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})")]
        if "visibility_scope" not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN visibility_scope VARCHAR(20)")
            print(f"{table}: added visibility_scope")
        else:
            print(f"{table}: visibility_scope already present")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS resource_visibility_targets (
            id CHAR(32) PRIMARY KEY,
            resource_kind VARCHAR(20) NOT NULL,
            resource_id CHAR(32) NOT NULL,
            student_id CHAR(32) NOT NULL REFERENCES students(id) ON DELETE CASCADE,
            created_by CHAR(32) REFERENCES users(id) ON DELETE SET NULL,
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_resource_target UNIQUE (resource_kind, resource_id, student_id)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_rv_targets_resource ON resource_visibility_targets (resource_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_rv_targets_student ON resource_visibility_targets (student_id)")
    print("resource_visibility_targets: ensured")

    # backfill (only rows without a scope yet)
    cur.execute("""
        UPDATE study_materials SET visibility_scope='students'
        WHERE visibility_scope IS NULL
          AND id IN (SELECT DISTINCT material_id FROM material_assignments)
    """)
    print(f"study_materials: {cur.rowcount} -> 'students' (explicit assignment)")
    cur.execute("""
        UPDATE study_materials SET visibility_scope='programme'
        WHERE visibility_scope IS NULL AND programme_id IS NOT NULL
    """)
    print(f"study_materials: {cur.rowcount} -> 'programme'")
    cur.execute("""
        UPDATE study_materials SET visibility_scope='all'
        WHERE visibility_scope IS NULL
    """)
    print(f"study_materials: {cur.rowcount} -> 'all' (was academy-wide already)")
    cur.execute("""
        UPDATE resource_recommendations SET visibility_scope='programme'
        WHERE visibility_scope IS NULL AND programme_id IS NOT NULL
    """)
    print(f"resource_recommendations: {cur.rowcount} -> 'programme'")
    cur.execute("""
        UPDATE resource_recommendations SET visibility_scope='all'
        WHERE visibility_scope IS NULL
    """)
    print(f"resource_recommendations: {cur.rowcount} -> 'all'")

    for t in ("study_materials", "resource_recommendations"):
        dist = list(cur.execute(f"SELECT visibility_scope, COUNT(*) FROM {t} GROUP BY 1"))
        print(f"{t} scopes:", dict(dist))
    con.close()
    print("MIGRATION OK")


if __name__ == "__main__":
    main()
