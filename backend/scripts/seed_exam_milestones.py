#!/usr/bin/env python3
"""Seed a realistic exam plan + milestone goals for every active student.

Forward-looking records only — a target grade, a submission window and the
goals that lead up to it. Results are NEVER written here: a result arrives
from the board (Trinity / Rockschool) and is entered when it is published.

For each active student with an active enrolment this creates, when missing:

  * one exam record      — board by programme, target grade by skill level,
                           submission deadline +5 weeks, exam window +7..+9 weeks
  * two milestone goals  — a studio performance and the repertoire to finish

Idempotent: a student who already has an exam, or a milestone with the same
title, is left untouched. Rerunning never duplicates anything.

Usage:
    cd backend
    python scripts/seed_exam_milestones.py --dry-run
    python scripts/seed_exam_milestones.py --apply
"""
import argparse
import asyncio
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.enrollment import Enrollment
from app.models.exam import Exam, Milestone
from app.models.student import Student

BOARDS = {
    "piano": "Trinity College London",
    "electronic_keyboard": "Trinity College London",
    "western_vocals": "Trinity College London",
    "music_theory": "Trinity College London",
    "acoustic_guitar": "Rockschool (RSL Awards)",
    "electric_guitar": "Rockschool (RSL Awards)",
    "bass_guitar": "Rockschool (RSL Awards)",
    "ukulele": "Rockschool (RSL Awards)",
    "indian_bansuri": "ChankArts Music Academy",
}
GRADE_BY_LEVEL = {"beginner": "Initial", "intermediate": "Grade 1", "advanced": "Grade 2"}
SEASONS = ["Winter", "Winter", "Spring", "Spring", "Spring", "Summer",
           "Summer", "Summer", "Autumn", "Autumn", "Autumn", "Winter"]

PERFORMANCE_GOAL = (
    "First studio performance",
    "A prepared piece played through, start to finish, in the studio.",
    "performance",
)


def target_session(window_end: date) -> str:
    return f"{SEASONS[window_end.month - 1]} {window_end.year}"


async def next_grade(db: AsyncSession, student_id, fallback: str) -> str:
    """The next grade up from whatever the student already holds.

    A certificate at Initial / Entry Level / Debut leads to Grade 1, Grade 1
    leads to Grade 2, and so on — a student is never re-planned for a grade
    they have already passed. Falls back to the skill level.
    """
    from app.models.achievement import Achievement

    held = (await db.execute(
        select(Achievement.grade_level).where(
            Achievement.student_id == student_id,
            Achievement.grade_level.isnot(None),
            Achievement.is_archived.is_(False),
        )
    )).scalars().all()

    top = 0
    for value in held:
        text = str(value).strip().lower()
        if text.startswith("grade ") and text[6:].isdigit():
            top = max(top, int(text[6:]))
    if top:
        return f"Grade {min(top + 1, 8)}"
    if any(str(v).strip().lower() in ("initial", "entry level", "debut") for v in held):
        return "Grade 1"
    return fallback


async def run(apply: bool) -> None:
    created_exams = created_goals = skipped = 0
    today = date.today()
    deadline = today + timedelta(days=35)
    window_start = today + timedelta(days=49)
    window_end = today + timedelta(days=63)

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(Student, Enrollment)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(Student.status == "active", Enrollment.status == "active")
            .order_by(Student.created_at.asc())
        )).all()

        for student, enrollment in rows:
            pid = enrollment.programme_id or ""
            board = BOARDS.get(pid, "ChankArts Music Academy")
            grade = await next_grade(
                db, student.id, GRADE_BY_LEVEL.get(student.skill_level or "", "Initial")
            )

            has_exam = (await db.execute(
                select(Exam.id).where(Exam.student_id == student.id).limit(1)
            )).first()
            if has_exam:
                skipped += 1
            else:
                name = f"{student.first_name} {student.last_name}"
                print(f"  + EXAM     {name}: {board} {grade} ({enrollment.programme_name})")
                if apply:
                    db.add(Exam(
                        student_id=student.id,
                        enrollment_id=enrollment.id,
                        board=board,
                        instrument=enrollment.programme_name,
                        grade=grade,
                        application_status="preparing",
                        payment_status="not_applicable",
                        exam_window_start=window_start,
                        exam_window_end=window_end,
                        submission_deadline=deadline,
                        submission_status="not_submitted",
                        readiness="ready" if (student.skill_level or "") == "advanced" else "developing",
                        result=None,                       # never invented
                        notes=f"Target session: {target_session(window_end)}",
                    ))
                created_exams += 1

            wanted = [
                (PERFORMANCE_GOAL[0], PERFORMANCE_GOAL[1], PERFORMANCE_GOAL[2], today + timedelta(days=28)),
                (f"Finish {grade} repertoire",
                 f"All {grade} pieces, scales and supporting tests ready for {board}.",
                 "assessment", deadline),
            ]
            for title, description, kind, due in wanted:
                exists = (await db.execute(
                    select(Milestone.id).where(
                        Milestone.student_id == student.id, Milestone.title == title
                    ).limit(1)
                )).first()
                if exists:
                    continue
                name = f"{student.first_name} {student.last_name}"
                print(f"  + GOAL     {name}: {title}")
                if apply:
                    db.add(Milestone(
                        student_id=student.id,
                        enrollment_id=enrollment.id,
                        title=title,
                        description=description,
                        milestone_type=kind,
                        due_date=due,
                        status="upcoming",                # a goal, not a claim
                        created_by=None,
                    ))
                created_goals += 1

        if apply:
            await db.commit()

    mode = "applied" if apply else "dry-run (no changes written)"
    print(f"\n{mode}: {created_exams} exam plan(s), {created_goals} milestone goal(s), "
          f"{skipped} student(s) already had an exam")
    if not apply:
        print("Re-run with --apply to write these records.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--dry-run", action="store_true", help="report only (default)")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
