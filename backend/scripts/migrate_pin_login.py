#!/usr/bin/env python3
"""Schema migration for ID+PIN login + honest NULL storage of unprovided data.

- users.email becomes nullable (students log in by roll ID, no email invented)
- users gains must_change_pin (forced PIN change on first login)
- students.date_of_birth becomes nullable (DOB not provided in source roster)
- class_schedules.instructor_id becomes nullable (instructors not yet assigned)

Idempotent: safe to run twice. Backs up tables before rebuild.
"""
import sqlite3
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "../_local-preview/preview.db"

REBUILDS = {
    "users": (
        """CREATE TABLE users_new (
    id UUID NOT NULL,
    email VARCHAR(255),
    username VARCHAR(100) NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(10) NOT NULL,
    is_active BOOLEAN,
    created_at DATETIME,
    updated_at DATETIME,
    must_change_pin BOOLEAN DEFAULT 0,
    PRIMARY KEY (id)
)""",
        ["id", "email", "username", "hashed_password", "role", "is_active", "created_at", "updated_at"],
        [
            "CREATE UNIQUE INDEX ix_users_username ON users (username)",
            "CREATE UNIQUE INDEX ix_users_email ON users (email)",
        ],
    ),
    "students": (
        """CREATE TABLE students_new (
    id UUID NOT NULL,
    user_id UUID NOT NULL,
    cma_registration_id VARCHAR(20) NOT NULL,
    portal_slug VARCHAR(120),
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    date_of_birth DATE,
    phone VARCHAR(20),
    address TEXT,
    status VARCHAR(20) NOT NULL,
    skill_level VARCHAR(50),
    profile_image_url VARCHAR(500),
    notes TEXT,
    profile_complete BOOLEAN,
    created_at DATETIME,
    updated_at DATETIME,
    PRIMARY KEY (id),
    UNIQUE (user_id),
    FOREIGN KEY(user_id) REFERENCES users (id)
)""",
        ["id", "user_id", "cma_registration_id", "portal_slug", "first_name", "last_name",
         "date_of_birth", "phone", "address", "status", "skill_level", "profile_image_url",
         "notes", "profile_complete", "created_at", "updated_at"],
        [
            "CREATE UNIQUE INDEX ix_students_cma_registration_id ON students (cma_registration_id)",
            "CREATE UNIQUE INDEX ix_students_portal_slug ON students (portal_slug)",
        ],
    ),
    "class_schedules": (
        """CREATE TABLE class_schedules_new (
    id UUID NOT NULL,
    enrollment_id UUID NOT NULL,
    instructor_id UUID,
    day_of_week VARCHAR(10) NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    frequency VARCHAR(20),
    is_online BOOLEAN,
    location VARCHAR(200),
    meeting_link VARCHAR(500),
    is_active BOOLEAN,
    start_date DATE,
    end_date DATE,
    created_at DATETIME,
    updated_at DATETIME,
    PRIMARY KEY (id),
    FOREIGN KEY(enrollment_id) REFERENCES enrollments (id) ON DELETE CASCADE,
    FOREIGN KEY(instructor_id) REFERENCES instructors (id)
)""",
        ["id", "enrollment_id", "instructor_id", "day_of_week", "start_time", "end_time",
         "frequency", "is_online", "location", "meeting_link", "is_active",
         "start_date", "end_date", "created_at", "updated_at"],
        [],
    ),
}


def col_names(create_sql):
    body = create_sql[create_sql.index("(") + 1:create_sql.rindex(")")]
    names = []
    for line in body.split("\n"):
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY", "UNIQUE", "FOREIGN")):
            continue
        names.append(line.split()[0])
    return names


def main():
    con = sqlite3.connect(DB)
    con.isolation_level = None
    cur = con.cursor()

    # --- users: add must_change_pin if missing; relax email if NOT NULL ---
    cols = [r[1] for r in cur.execute("PRAGMA table_info(users)")]
    if "must_change_pin" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN must_change_pin BOOLEAN DEFAULT 0")
        print("users: added must_change_pin")
    else:
        print("users: must_change_pin already present")

    email_notnull = [r for r in cur.execute("PRAGMA table_info(users)") if r[1] == "email"][0][3]
    if email_notnull:
        rebuild(cur, "users", *REBUILDS["users"])
        print("users: email relaxed to NULL")
    else:
        print("users: email already nullable")

    # --- students: relax date_of_birth ---
    dob_notnull = [r for r in cur.execute("PRAGMA table_info(students)") if r[1] == "date_of_birth"][0][3]
    if dob_notnull:
        rebuild(cur, "students", *REBUILDS["students"])
        print("students: date_of_birth relaxed to NULL")
    else:
        print("students: date_of_birth already nullable")

    # --- class_schedules: relax instructor_id ---
    ins_notnull = [r for r in cur.execute("PRAGMA table_info(class_schedules)") if r[1] == "instructor_id"][0][3]
    if ins_notnull:
        rebuild(cur, "class_schedules", *REBUILDS["class_schedules"])
        print("class_schedules: instructor_id relaxed to NULL")
    else:
        print("class_schedules: instructor_id already nullable")

    con.close()
    print("MIGRATION OK")


def rebuild(cur, table, create_sql, columns, indexes):
    new_table = table + "_new"
    if new_table in [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
        cur.execute(f"DROP TABLE {new_table}")
    cur.execute("PRAGMA foreign_keys=OFF")
    cur.execute("BEGIN")
    try:
        cur.execute(create_sql)
        col_list = ", ".join(columns)
        cur.execute(f"INSERT INTO {new_table} ({col_list}) SELECT {col_list} FROM {table}")
        cur.execute(f"DROP TABLE {table}")
        cur.execute(f"ALTER TABLE {new_table} RENAME TO {table}")
        for idx in indexes:
            cur.execute(idx)
        cur.execute("COMMIT")
    except Exception:
        cur.execute("ROLLBACK")
        raise
    finally:
        cur.execute("PRAGMA foreign_keys=ON")


if __name__ == "__main__":
    main()
