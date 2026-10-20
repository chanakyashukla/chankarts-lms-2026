#!/usr/bin/env python3
"""Materialise dated class sessions from the established weekly timetable.

Reads active rows from class_schedules (the academy's confirmed timetable)
and inserts upcoming class_sessions occurrences:
  - from the current week's Monday (academy timezone, Asia/Kolkata) through +180 days
  - weekday + time taken from each timetable row (no invented schedules)
  - status = 'scheduled' only — generated sessions are NEVER marked completed
  - idempotent: a (enrolment, date, start) triple is inserted at most once,
    so re-runs and calendar re-renders never create duplicates

Usage: DATABASE_URL=... python3 scripts/seed_class_sessions.py
"""
import asyncio
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, func

from app.database import AsyncSessionLocal, engine, Base
import app.models  # noqa: F401
from app.models.class_schedule import ClassSchedule
from app.models.enrollment import Enrollment
from app.models.session import ClassSession, SessionStatus

ACADEMY_TZ = ZoneInfo("Asia/Kolkata")
HORIZON_DAYS = 180
DAY_INDEX = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
             "friday": 4, "saturday": 5, "sunday": 6}


def minutes_between(start: time, end: time) -> int:
    return int((datetime.combine(date(2000, 1, 1), end)
                - datetime.combine(date(2000, 1, 1), start)).total_seconds() // 60)


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    today = datetime.now(ACADEMY_TZ).date()
    # Start at the beginning of the current week (Monday) so the Week/Month
    # views have full context from day one. Earlier-week occurrences are part
    # of the confirmed recurring timetable; they stay 'scheduled' (never
    # auto-completed) until faculty acts on them.
    week_start = today - timedelta(days=today.weekday())
    horizon = today + timedelta(days=HORIZON_DAYS)

    created = 0
    skipped_existing = 0
    per_student = {}

    async with AsyncSessionLocal() as db:
        schedules = (await db.execute(
            select(ClassSchedule, Enrollment)
            .join(Enrollment, Enrollment.id == ClassSchedule.enrollment_id)
            .where(ClassSchedule.is_active.is_(True))
        )).all()

        for sched, enr in schedules:
            day_idx = DAY_INDEX.get((sched.day_of_week or "").lower())
            if day_idx is None:
                print(f"  ! skip schedule {str(sched.id)[:8]}: unknown day {sched.day_of_week!r}")
                continue

            # first occurrence on/after the current week's Monday
            cursor = week_start + timedelta(days=(day_idx - week_start.weekday()) % 7)
            while cursor <= horizon:
                exists = (await db.execute(
                    select(func.count(ClassSession.id)).where(
                        ClassSession.enrollment_id == enr.id,
                        ClassSession.scheduled_date == cursor,
                        ClassSession.scheduled_start == sched.start_time,
                    )
                )).scalar_one()
                if exists:
                    skipped_existing += 1
                else:
                    db.add(ClassSession(
                        enrollment_id=enr.id,
                        student_id=enr.student_id,
                        instructor_id=sched.instructor_id,   # may be NULL (not yet assigned)
                        scheduled_date=cursor,
                        scheduled_start=sched.start_time,
                        scheduled_end=sched.end_time,
                        timezone="Asia/Kolkata",
                        duration_minutes=minutes_between(sched.start_time, sched.end_time),
                        status=SessionStatus.SCHEDULED,     # never auto-completed
                        is_online=bool(sched.is_online),
                        location=sched.location,
                        meeting_link=sched.meeting_link,
                        counts_toward_package=True,
                        billing_month=cursor.strftime("%Y-%m"),
                    ))
                    created += 1
                    key = str(enr.id)
                    per_student.setdefault(key, []).append(cursor)
                cursor += timedelta(days=7)

            await db.commit()  # per-schedule commit keeps re-runs safe

    print("=== CLASS SESSION SEED REPORT ===")
    print(f"window: {week_start} .. {horizon} (Asia/Kolkata, current week start +{HORIZON_DAYS}d)")
    print(f"sessions created: {created}   already existed (skipped): {skipped_existing}")
    async with AsyncSessionLocal() as db:
        dist = (await db.execute(
            select(ClassSession.status, func.count()).group_by(ClassSession.status)
        )).all()
        print("status distribution:", {str(k): v for k, v in dist})

    async with AsyncSessionLocal() as db:
        # per-student summary for the roster
        rows = (await db.execute(
            select(Enrollment.id, Enrollment.programme_name, func.count(ClassSession.id))
            .outerjoin(ClassSession, ClassSession.enrollment_id == Enrollment.id)
            .group_by(Enrollment.id, Enrollment.programme_name)
        )).all()
        print("sessions per enrolment:")
        for eid, prog, n in rows:
            print(f"  {prog}: {n}")


if __name__ == "__main__":
    asyncio.run(main())
