#!/usr/bin/env python3
"""Additive migration: class completion & reschedule states.

1. class_sessions.practice_recommendations (Text, nullable)
2. Confirmed reschedules: original occurrences that already have a
   replacement row (another session with replaces_session_id = original.id)
   move from 'rescheduling_required' to the new 'rescheduled' state.
   Nothing else is touched; idempotent.

Usage: python3 scripts/migrate_class_completion.py <path-to.db>
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "../_local-preview/preview.db"


def main():
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()

    cols = [r[1] for r in cur.execute("PRAGMA table_info(class_sessions)")]
    if "practice_recommendations" not in cols:
        cur.execute("ALTER TABLE class_sessions ADD COLUMN practice_recommendations TEXT")
        print("class_sessions: added practice_recommendations")
    else:
        print("class_sessions: practice_recommendations already present")

    cur.execute("""
        UPDATE class_sessions SET status='rescheduled'
        WHERE status='rescheduling_required'
          AND id IN (SELECT replaces_session_id FROM class_sessions
                     WHERE replaces_session_id IS NOT NULL)
    """)
    moved = cur.rowcount
    print(f"class_sessions: {moved} confirmed-reschedule original(s) moved to 'rescheduled'")

    dist = list(cur.execute("SELECT status, COUNT(*) FROM class_sessions GROUP BY status"))
    print("status distribution:", dict((k or 'NULL', v) for k, v in dist))
    con.close()
    print("MIGRATION OK")


if __name__ == "__main__":
    main()
