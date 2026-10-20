#!/usr/bin/env python3
"""Assign monthly fee packages from the established academy timetable.

The confirmed register assigns packages by class frequency:
  1 class per week  -> 4 classes / month  (fee_plan=4_classes,  ₹4,500)
  2 classes per week -> 8 classes / month  (fee_plan=8_classes,  ₹8,000)

Rules:
- Fills fee_plan ONLY where it is currently NULL (never alters an
  existing assignment, never touches payment records).
- Derives from active class_schedules of the enrolment — no names.
- Enrolments with no timetable are left unassigned (no payment button).
- Idempotent / repeatable.

Usage: DATABASE_URL=... python3 scripts/seed_package_assignments.py
"""
import asyncio
from datetime import date, time, datetime

from sqlalchemy import select, func, and_

from app.database import AsyncSessionLocal, engine, Base
import app.models  # noqa: F401
from app.models.enrollment import Enrollment
from app.models.class_schedule import ClassSchedule

PLANS = {
    1: ("4_classes", 4500.00),
    2: ("8_classes", 8000.00),
}


async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Enrollment)
            .where(Enrollment.fee_plan.is_(None))
        )).scalars().all()

        assigned, skipped_no_schedule = [], 0
        for enr in rows:
            week_count = (await db.execute(
                select(func.count(ClassSchedule.id)).where(
                    ClassSchedule.enrollment_id == enr.id,
                    ClassSchedule.is_active.is_(True),
                )
            )).scalar_one()

            if week_count == 0:
                skipped_no_schedule += 1
                continue

            plan_key = min(week_count, 2)  # 1->4_classes, 2+->8_classes
            plan, amount = PLANS[plan_key]
            enr.fee_plan = plan
            enr.fee_amount = amount
            db.add(enr)
            assigned.append((str(enr.id)[:8], enr.programme_name, week_count, plan))

        await db.commit()

    print("=== PACKAGE ASSIGNMENT REPORT (NULLs only) ===")
    print(f"assigned: {len(assigned)}  |  left unassigned (no timetable): {skipped_no_schedule}  |  already set (untouched): see below")
    for e8, prog, wk, plan in assigned:
        print(f"  enrolment {e8} · {prog} · {wk} class(es)/week -> {plan}")

    async with AsyncSessionLocal() as db:
        dist = (await db.execute(
            select(Enrollment.fee_plan, func.count()).group_by(Enrollment.fee_plan)
        )).all()
        print("final distribution:", {str(k): v for k, v in dist})


if __name__ == "__main__":
    asyncio.run(main())
