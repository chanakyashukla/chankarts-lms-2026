#!/usr/bin/env python3
"""Provision the real ChankArts Music Academy roster into the existing LMS.

- Reads credentials from CSVs kept OUTSIDE the repo (mode 600).
- Stores PINs only as hashes; never prints or logs a PIN.
- Idempotent: existing accounts/schedules are never duplicated or reset.
- Generates a missing-information report; invents no data.

Usage (from backend/):
  DATABASE_URL=sqlite+aiosqlite:///../_local-preview/preview.db \
    python3 scripts/provision_roster.py <accounts.csv> <timetable.csv>
"""
import asyncio
import csv
import io
import re
import sys
from datetime import date, time

from sqlalchemy import select

from app.database import AsyncSessionLocal, engine, Base
import app.models  # noqa: F401  (register all tables)
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.models.user import User
from app.models.admin import Admin
from app.models.student import Student
from app.models.enrollment import Enrollment
from app.models.instructor import Instructor
from app.models.class_schedule import ClassSchedule

PROGRAMME_SLUGS = {
    "western vocals": "western_vocals",
    "electronic keyboard": "electronic_keyboard",
    "ukulele": "ukulele",
    "acoustic guitar": "acoustic_guitar",
    "piano": "piano",
}


def read_rows(path):
    with io.open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def hhmm(value):
    h, m = value.strip().split(":")
    return time(int(h), int(m))


async def main(accounts_path, timetable_path):
    accounts = read_rows(accounts_path)
    timetable = read_rows(timetable_path)

    report = {
        "users_created": 0, "users_existing": 0,
        "students_created": 0, "students_existing": 0,
        "admins_created": 0,
        "enrollments_created": 0, "enrollments_existing": 0,
        "schedules_created": 0, "schedules_existing": 0,
        "conflicts": [], "missing": [],
    }

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # ---------- accounts ----------
        user_by_login = {}
        for idx, row in enumerate(accounts, start=1):
            username = row["username"].strip()
            role = row["role"].strip().lower()
            pin = row["pin"].strip()
            if not re.fullmatch(r"\d{4}", pin):
                raise SystemExit(f"FATAL: PIN for {username} is not exactly 4 digits")

            existing = (
                await db.execute(select(User).where(User.username == username))
            ).scalar_one_or_none()

            if existing:
                report["users_existing"] += 1
                user = existing
            else:
                user = User(
                    email=None,  # no email invented; ID + PIN login
                    username=username,
                    hashed_password=get_password_hash(pin),
                    role=UserRole.ADMIN if role == "admin" else UserRole.STUDENT,
                    is_active=True,
                    must_change_pin=True,  # forced change on first login
                )
                db.add(user)
                await db.flush()
                report["users_created"] += 1
            user_by_login[username] = user

            if role == "admin":
                has_profile = (
                    await db.execute(select(Admin).where(Admin.user_id == user.id))
                ).scalar_one_or_none()
                if not has_profile:
                    db.add(Admin(
                        user_id=user.id,
                        first_name=row["first_name"].strip(),
                        last_name=row["last_name"].strip() or "User",
                        admin_level="super_admin",
                        is_active=True,
                    ))
                    report["admins_created"] += 1
                continue

            # ----- student profile -----
            student = (
                await db.execute(select(Student).where(Student.user_id == user.id))
            ).scalar_one_or_none()
            if student:
                report["students_existing"] += 1
            else:
                # stable sequential CMA-YYYY-#### based on CSV order
                cma_id = f"CMA-{date.today().year}-{idx:04d}"
                taken = (
                    await db.execute(
                        select(Student).where(Student.cma_registration_id == cma_id)
                    )
                ).scalar_one_or_none()
                if taken:
                    raise SystemExit(f"FATAL: CMA id collision {cma_id}")
                student = Student(
                    user_id=user.id,
                    cma_registration_id=cma_id,
                    portal_slug=username.lower(),
                    first_name=row["first_name"].strip(),
                    last_name=row["last_name"].strip(),  # "" when surname not provided
                    date_of_birth=None,   # not provided in source roster
                    phone=None,           # not provided
                    status="active",
                    skill_level=None,     # not provided
                    profile_complete=False,
                    notes=("Provisioned from consolidated roster. "
                           "Missing: date of birth, phone, parent/guardian link."),
                )
                db.add(student)
                await db.flush()
                report["students_created"] += 1

            # ----- enrollment (instrument from roster; instructor/package unset) -----
            instrument = (row.get("instrument") or "").strip()
            if instrument:
                slug = PROGRAMME_SLUGS.get(instrument.lower())
                if not slug:
                    raise SystemExit(f"FATAL: unknown instrument '{instrument}'")
                enr = (
                    await db.execute(select(Enrollment).where(
                        Enrollment.student_id == student.id,
                        Enrollment.programme_id == slug,
                    ))
                ).scalar_one_or_none()
                if enr:
                    report["enrollments_existing"] += 1
                else:
                    enr = Enrollment(
                        student_id=student.id,
                        programme_id=slug,
                        programme_name=instrument,
                        instructor_id=None,   # not provided in roster
                        fee_plan=None,        # package not confirmed
                        fee_amount=None,      # not provided
                        status="active",
                        start_date=None,      # not provided
                        notes="Instructor and monthly package pending confirmation.",
                    )
                    db.add(enr)
                    await db.flush()
                    report["enrollments_created"] += 1

        # ---------- weekly timetable ----------
        for row in timetable:
            username = row["username"].strip()
            user = user_by_login.get(username)
            if not user:
                raise SystemExit(f"FATAL: timetable references unknown {username}")
            student = (
                await db.execute(select(Student).where(Student.user_id == user.id))
            ).scalar_one_or_none()
            enr = (
                await db.execute(select(Enrollment).where(
                    Enrollment.student_id == student.id
                ))
            ).scalars().first()
            if not enr:
                raise SystemExit(f"FATAL: no enrollment for {username}")

            start, end = hhmm(row["start"]), hhmm(row["end"])
            dup = (
                await db.execute(select(ClassSchedule).where(
                    ClassSchedule.enrollment_id == enr.id,
                    ClassSchedule.day_of_week == row["day"].strip().lower(),
                    ClassSchedule.start_time == start,
                    ClassSchedule.end_time == end,
                ))
            ).scalar_one_or_none()
            if dup:
                report["schedules_existing"] += 1
                continue

            db.add(ClassSchedule(
                enrollment_id=enr.id,
                instructor_id=None,        # instructors not assigned yet
                day_of_week=row["day"].strip().lower(),
                start_time=start,
                end_time=end,
                frequency="weekly",
                is_active=True,
                start_date=None,           # effective date not provided
            ))
            report["schedules_created"] += 1

        await db.commit()

        # ---------- conflict detection (never auto-resolved) ----------
        rows = (
            await db.execute(
                select(ClassSchedule, Enrollment, Student)
                .join(Enrollment, Enrollment.id == ClassSchedule.enrollment_id)
                .join(Student, Student.id == Enrollment.student_id)
            )
        ).all()
        active = [(cs, stu) for cs, stu in (
            (cs, stu) for cs, _e, stu in rows
        ) if cs.is_active]
        for i in range(len(active)):
            for j in range(i + 1, len(active)):
                a, sa = active[i]
                b, sb = active[j]
                if a.day_of_week != b.day_of_week:
                    continue
                if a.start_time < b.end_time and b.start_time < a.end_time:
                    report["conflicts"].append(
                        f"{a.day_of_week.title()}: {sa.full_name} "
                        f"{a.start_time.strftime('%H:%M')}-{a.end_time.strftime('%H:%M')} "
                        f"OVERLAPS {sb.full_name} "
                        f"{b.start_time.strftime('%H:%M')}-{b.end_time.strftime('%H:%M')}"
                    )

        # ---------- missing-information report ----------
        students = (await db.execute(select(Student))).scalars().all()
        no_dob = sum(1 for s in students if s.date_of_birth is None)
        no_phone = sum(1 for s in students if not s.phone)
        no_surname = [s.first_name for s in students if not s.last_name]
        enrollments = (await db.execute(select(Enrollment))).scalars().all()
        no_instructor = sum(1 for e in enrollments if e.instructor_id is None)
        no_package = sum(1 for e in enrollments if e.fee_plan is None)
        report["missing"] = [
            f"date_of_birth missing: {no_dob} students (schema stores NULL, flagged)",
            f"phone missing: {no_phone} students",
            f"surname missing: {', '.join(no_surname) or 'none'}",
            f"parent/guardian links missing: {no_dob} students (none provided)",
            f"instructor not assigned: {no_instructor} enrollments / all timetable rows",
            f"monthly package (4/8 class plan) not confirmed: {no_package} enrollments",
            "schedule effective date not provided (stored NULL)",
            "monthly dated class entries + holiday calendar: pending your confirmation "
            "(not generated — would invent holiday data)",
            "login emails: none (by design — ID + PIN login; users.email is NULL)",
        ]

    print("=== PROVISIONING REPORT ===")
    for k in ("users_created", "users_existing", "admins_created",
              "students_created", "students_existing",
              "enrollments_created", "enrollments_existing",
              "schedules_created", "schedules_existing"):
        print(f"{k}: {report[k]}")
    print(f"conflicts_detected: {len(report['conflicts'])}")
    for c in report["conflicts"]:
        print(f"  ⚠ {c}")
    print("missing_information:")
    for m in report["missing"]:
        print(f"  - {m}")
    print("(PINs never printed; stored as hashes only)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    asyncio.run(main(sys.argv[1], sys.argv[2]))
