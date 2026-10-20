"""
Student / parent portal: profile, dashboard aggregates, children, notifications.
Every number here is computed from real records — nothing is hard-coded.
"""
from datetime import date, datetime, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.roles import UserRole
from app.database import get_db
from app.models.billing import Invoice
from app.models.enrollment import Enrollment
from app.models.exam import Exam, Milestone
from app.models.guardian import Guardian, GuardianAccount
from app.models.instructor import Instructor
from app.models.learning import Assignment, MaterialAssignment, StudyMaterial
from app.models.notification import Notification
from app.models.reports import MonthlyReport
from app.models.session import ClassSession, SessionStatus
from app.models.student import Student
from app.models.syllabus import StudentSyllabusProgress, Syllabus, SyllabusItem
from app.models.user import User
from app.services.access import (
    get_instructor_for_user,
    get_linked_student_ids,
    require_student_access,
)
from app.services.notifications import mark_notifications_read

router = APIRouter()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _month_bounds(month: Optional[str] = None) -> tuple[date, date, str]:
    month = month or date.today().strftime("%Y-%m")
    try:
        year, mon = int(month.split("-")[0]), int(month.split("-")[1])
        start = date(year, mon, 1)
        end = date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1) - timedelta(days=1)
        return start, end, month
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid month. Use YYYY-MM.")


async def _student_basics(db: AsyncSession, student_id: UUID) -> Optional[dict]:
    result = await db.execute(
        select(Student, User.email)
        .join(User, User.id == Student.user_id)
        .where(Student.id == student_id)
    )
    row = result.first()
    if not row:
        return None
    student, email = row
    return {
        "id": str(student.id),
        "first_name": student.first_name,
        "last_name": student.last_name,
        "full_name": student.full_name,
        "cma_registration_id": student.cma_registration_id,
        "portal_slug": student.portal_slug,
        "email": email,
        "phone": student.phone,
        "address": student.address,
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
        "status": student.status,
        "skill_level": student.skill_level,
    }


async def _enrollments_payload(db: AsyncSession, student_id: UUID) -> List[dict]:
    result = await db.execute(
        select(Enrollment)
        .options(selectinload(Enrollment.instructor))
        .where(Enrollment.student_id == student_id)
        .order_by(Enrollment.created_at.asc())
    )
    payload = []
    for e in result.scalars().all():
        instructor_name = None
        if e.instructor:
            instructor_name = f"{e.instructor.first_name} {e.instructor.last_name}"
        payload.append(
            {
                "id": str(e.id),
                "programme_id": e.programme_id,
                "programme_name": e.programme_name,
                "status": e.status,
                "fee_plan": e.fee_plan,
                "fee_amount": float(e.fee_amount) if e.fee_amount else None,
                "start_date": e.start_date.isoformat() if e.start_date else None,
                "instructor": instructor_name,
                "instructor_id": str(e.instructor_id) if e.instructor_id else None,
            }
        )
    return payload


# ------------------------------------------------------------------
# Identity
# ------------------------------------------------------------------
@router.get("/me")
async def portal_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Profile bundle for the signed-in student or parent."""
    if current_user.role == UserRole.PARENT:
        student_ids = await get_linked_student_ids(db, current_user)
        children = []
        for sid in student_ids:
            basics = await _student_basics(db, sid)
            if basics:
                basics["enrollments"] = await _enrollments_payload(db, sid)
                children.append(basics)
        return {
            "role": "parent",
            "user_id": str(current_user.id),
            "email": current_user.email,
            "children": children,
        }

    if current_user.role == UserRole.STUDENT:
        result = await db.execute(select(Student).where(Student.user_id == current_user.id))
        student = result.scalar_one_or_none()
        if not student:
            raise HTTPException(status_code=404, detail="Student profile not found")
        basics = await _student_basics(db, student.id)
        basics["enrollments"] = await _enrollments_payload(db, student.id)
        guardians_result = await db.execute(
            select(Guardian).where(Guardian.student_id == student.id)
        )
        basics["guardians"] = [
            {
                "name": g.full_name,
                "relationship": g.guardian_relationship,
                "phone": g.phone,
                "email": g.email,
            }
            for g in guardians_result.scalars().all()
        ]
        return {"role": "student", "user_id": str(current_user.id), "email": current_user.email, "student": basics}

    if current_user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, current_user)
        return {
            "role": "instructor",
            "user_id": str(current_user.id),
            "email": current_user.email,
            "instructor": {
                "id": str(instructor.id) if instructor else None,
                "name": f"{instructor.first_name} {instructor.last_name}" if instructor else None,
                "specializations": instructor.specializations if instructor else None,
                "qualifications": instructor.qualifications if instructor else None,
                "experience_years": instructor.experience_years if instructor else None,
                "phone": instructor.phone if instructor else None,
                "bio": instructor.bio if instructor else None,
                "is_active": bool(instructor.is_active) if instructor else None,
            },
        }

    return {"role": current_user.role.value, "user_id": str(current_user.id), "email": current_user.email}


@router.get("/by-slug/{slug}")
async def portal_by_slug(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Personalised route support (`/academy/prakhyaat-verma`).

    The slug is a navigation convenience only — the signed-in user must still
    be the student or a linked guardian.
    """
    result = await db.execute(select(Student).where(Student.portal_slug == slug))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Not found")
    await require_student_access(db, current_user, student.id)
    basics = await _student_basics(db, student.id)
    basics["enrollments"] = await _enrollments_payload(db, student.id)
    return basics


class SelfProfileUpdate(BaseModel):
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    address: Optional[str] = Field(None, max_length=1000)


@router.patch("/profile")
async def update_own_profile(
    body: SelfProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Students may edit only permitted contact fields; identity fields are protected."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can update this profile")
    result = await db.execute(select(Student).where(Student.user_id == current_user.id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student profile not found")

    data = body.model_dump(exclude_unset=True)
    if "phone" in data and data["phone"]:
        import re
        cleaned = re.sub(r"[\s\-\(\)]", "", data["phone"])
        if not re.match(r"^\+?[\d]{10,15}$", cleaned):
            raise HTTPException(status_code=400, detail="Invalid phone number")

    for field, value in data.items():
        setattr(student, field, value)
    await db.flush()
    return await _student_basics(db, student.id)


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------
@router.get("/dashboard")
async def dashboard(
    student_id: Optional[UUID] = None,
    month: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    linked = await get_linked_student_ids(db, current_user)
    if not linked:
        raise HTTPException(status_code=403, detail="No student records are linked to this account")
    if student_id:
        await require_student_access(db, current_user, student_id)
        target = student_id
    else:
        target = linked[0]

    month_start, month_end, month_label = _month_bounds(month)
    basics = await _student_basics(db, target)
    enrollments = await _enrollments_payload(db, target)

    # Session aggregates for the billing month (actual status counts)
    counts = {s: 0 for s in (SessionStatus.COMPLETED, SessionStatus.SCHEDULED, SessionStatus.RESCHEDULING_REQUIRED, SessionStatus.CANCELLED)}
    session_rows = await db.execute(
        select(ClassSession).where(
            ClassSession.student_id == target,
            ClassSession.scheduled_date >= month_start,
            ClassSession.scheduled_date <= month_end,
        )
    )
    for s in session_rows.scalars().all():
        counts[s.status] = counts.get(s.status, 0) + 1

    upcoming_rows = await db.execute(
        select(ClassSession)
        .where(
            ClassSession.student_id == target,
            ClassSession.status.in_([SessionStatus.SCHEDULED, SessionStatus.RESCHEDULING_REQUIRED]),
            ClassSession.scheduled_date >= date.today(),
        )
        .order_by(ClassSession.scheduled_date.asc(), ClassSession.scheduled_start.asc())
        .limit(8)
    )
    upcoming = [
        {
            "id": str(s.id),
            "date": s.scheduled_date.isoformat(),
            "start": s.scheduled_start.strftime("%H:%M"),
            "end": s.scheduled_end.strftime("%H:%M"),
            "status": s.status,
            "programme": next((e["programme_name"] for e in enrollments if e["id"] == str(s.enrollment_id)), None),
        }
        for s in upcoming_rows.scalars().all()
    ]

    # Fee status for this month
    invoice_result = await db.execute(
        select(Invoice).where(
            Invoice.student_id == target,
            Invoice.billing_month == month_label,
        )
    )
    invoice = invoice_result.scalars().first()
    fee_payload = None
    if invoice:
        fee_payload = {
            "invoice_number": invoice.invoice_number,
            "amount_paise": invoice.amount_paise,
            "amount_paid_paise": invoice.amount_paid_paise,
            "outstanding_paise": max(invoice.amount_paise - invoice.amount_paid_paise, 0),
            "status": invoice.status,
        }

    # Latest published report
    report_result = await db.execute(
        select(MonthlyReport)
        .where(MonthlyReport.student_id == target, MonthlyReport.status == "published")
        .order_by(MonthlyReport.report_month.desc(), MonthlyReport.revision.desc())
        .limit(1)
    )
    latest_report = report_result.scalars().first()
    report_payload = None
    if latest_report:
        report_payload = {
            "id": str(latest_report.id),
            "report_month": latest_report.report_month,
            "progress_summary": latest_report.progress_summary,
            "topics_covered": latest_report.topics_covered,
            "strengths": latest_report.strengths,
            "areas_for_improvement": latest_report.areas_for_improvement,
            "next_month_focus": latest_report.next_month_focus,
            "published_at": latest_report.published_at.isoformat() if latest_report.published_at else None,
        }

    pending_assignments = await db.execute(
        select(Assignment).where(
            Assignment.student_id == target,
            Assignment.status.in_(["assigned", "revision_requested"]),
        )
    )
    pending_assignment_count = len(pending_assignments.scalars().all())

    # Syllabus progress (real completed/total)
    progress_rows = await db.execute(
        select(StudentSyllabusProgress).where(StudentSyllabusProgress.student_id == target)
    )
    progress = list(progress_rows.scalars().all())
    syllabus_completed = sum(1 for p in progress if p.status == "completed")
    syllabus_total = len(progress)

    exam_rows = await db.execute(
        select(Exam)
        .where(Exam.student_id == target, Exam.submission_status != "submitted")
        .order_by(Exam.submission_deadline.asc().nullslast())
        .limit(3)
    )
    upcoming_exams = [
        {
            "id": str(x.id),
            "board": x.board,
            "grade": x.grade,
            "instrument": x.instrument,
            "submission_deadline": x.submission_deadline.isoformat() if x.submission_deadline else None,
            "submission_status": x.submission_status,
            "readiness": x.readiness,
        }
        for x in exam_rows.scalars().all()
    ]

    return {
        "student": basics,
        "enrollments": enrollments,
        "month": month_label,
        "month_summary": {
            "completed": counts[SessionStatus.COMPLETED],
            "scheduled": counts[SessionStatus.SCHEDULED],
            "rescheduling_required": counts[SessionStatus.RESCHEDULING_REQUIRED],
            "cancelled": counts[SessionStatus.CANCELLED],
        },
        "upcoming_classes": upcoming,
        "fee": fee_payload,
        "latest_report": report_payload,
        "pending_assignments": pending_assignment_count,
        "syllabus": {
            "completed": syllabus_completed,
            "total": syllabus_total,
            "percent": round((syllabus_completed / syllabus_total) * 100) if syllabus_total else None,
        },
        "upcoming_exams": upcoming_exams,
        "linked_students": [str(s) for s in linked],
    }


# ------------------------------------------------------------------
# Parent helpers
# ------------------------------------------------------------------
@router.get("/children")
async def list_children(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.PARENT, UserRole.ADMIN):
        raise HTTPException(status_code=403, detail="Only guardian accounts have linked children")
    student_ids = await get_linked_student_ids(db, current_user)
    children = []
    for sid in student_ids:
        basics = await _student_basics(db, sid)
        if basics:
            basics["enrollments"] = await _enrollments_payload(db, sid)
            children.append(basics)
    return children


# ------------------------------------------------------------------
# Enrollments (role-scoped)
# ------------------------------------------------------------------
@router.get("/enrollments")
async def list_enrollments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enrollments the signed-in account is allowed to see:
    - student / parent → linked students' enrolments
    - instructor → their own teaching load (with student names)
    - admin → all
    """
    query = (
        select(Enrollment, Student)
        .join(Student, Student.id == Enrollment.student_id)
        .options(selectinload(Enrollment.instructor))
    )

    if current_user.role in (UserRole.STUDENT, UserRole.PARENT):
        linked = await get_linked_student_ids(db, current_user)
        query = query.where(Enrollment.student_id.in_(linked or [UUID(int=0)]))
    elif current_user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, current_user)
        if not instructor:
            return []
        query = query.where(Enrollment.instructor_id == instructor.id)
    elif current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    query = query.order_by(Enrollment.created_at.asc())
    result = await db.execute(query)
    return [
        {
            "id": str(enrollment.id),
            "student_id": str(student.id),
            "student_name": student.full_name,
            "cma_registration_id": student.cma_registration_id,
            "programme_id": enrollment.programme_id,
            "programme_name": enrollment.programme_name,
            "status": enrollment.status,
            "fee_plan": enrollment.fee_plan,
            "fee_amount": float(enrollment.fee_amount) if enrollment.fee_amount else None,
            "start_date": enrollment.start_date.isoformat() if enrollment.start_date else None,
            "instructor": (
                f"{enrollment.instructor.first_name} {enrollment.instructor.last_name}"
                if enrollment.instructor
                else None
            ),
            "instructor_id": str(enrollment.instructor_id) if enrollment.instructor_id else None,
        }
        for enrollment, student in result.all()
    ]


# ------------------------------------------------------------------
# Notifications
# ------------------------------------------------------------------
@router.get("/notifications")
async def list_notifications(
    unread_only: bool = False,
    limit: int = Query(50, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Notification).where(Notification.user_id == current_user.id)
    if unread_only:
        query = query.where(Notification.read_at.is_(None))
    query = query.order_by(Notification.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return [
        {
            "id": str(n.id),
            "type": n.type,
            "title": n.title,
            "body": n.body,
            "status": n.status,
            "read": n.read_at is not None,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in result.scalars().all()
    ]


@router.post("/notifications/read")
async def mark_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = await mark_notifications_read(db, current_user.id)
    return {"marked_read": count}
