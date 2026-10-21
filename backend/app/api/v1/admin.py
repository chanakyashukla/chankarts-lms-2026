from fastapi import APIRouter, Depends, HTTPException, Request, status, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, update, or_
from sqlalchemy.exc import IntegrityError, DBAPIError
from typing import List, Optional
from uuid import UUID
from datetime import datetime, date
import re

from app.database import get_db, Base
from app.models.user import User
from app.models.student import Student
from app.models.guardian import Guardian, GuardianAccount
from app.models.registration_request import RegistrationRequest, RegistrationRequestStatus
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.fee_record import FeeRecord, PaymentStatus
from app.models.attendance import Attendance
from app.models.progress import Progress
from app.models.instructor import Instructor
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.api.deps import require_role
from app.models.class_schedule import ClassSchedule
from app.services.ids import CMAIdService
from app.services.audit import record_audit
from app.services.notifications import notify_user
from app.services.email import email_service
from app.config import get_settings
import secrets
import uuid
from datetime import time as dtime
from app.models.pin_reset import PinResetRequest, PinResetRequestStatus
from app.models.session import ClassSession, SessionStatus, SessionStatusHistory
from app.models.learning import Assignment
from app.models.user import User as _UserForType

router = APIRouter()
settings = get_settings()


# ========================================
# Dashboard Stats
# ========================================
@router.get("/dashboard/stats")
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    # Total students
    student_count = await db.execute(select(func.count(Student.id)))
    total_students = student_count.scalar() or 0
    
    # Pending registrations
    pending_reg = await db.execute(
        select(func.count(RegistrationRequest.id)).where(
            RegistrationRequest.status == RegistrationRequestStatus.PENDING
        )
    )
    pending_registrations = pending_reg.scalar() or 0
    
    # Active enrollments
    active_enroll = await db.execute(
        select(func.count(Enrollment.id)).where(
            Enrollment.status == EnrollmentStatus.ACTIVE
        )
    )
    active_enrollments = active_enroll.scalar() or 0
    
    # Pending fees
    pending_fees = await db.execute(
        select(func.count(FeeRecord.id)).where(
            FeeRecord.payment_status == PaymentStatus.PENDING
        )
    )
    pending_fee_records = pending_fees.scalar() or 0
    
    # Recent registrations (last 5)
    recent_regs = await db.execute(
        select(RegistrationRequest)
        .order_by(RegistrationRequest.submitted_at.desc())
        .limit(5)
    )
    recent_registrations = []
    for reg in recent_regs.scalars().all():
        recent_registrations.append({
            "id": str(reg.id),
            "request_id": reg.request_id,
            "full_name": reg.full_name,
            "email": reg.email,
            "status": reg.status,
            "submitted_at": reg.submitted_at.isoformat() if reg.submitted_at else None,
        })
    
    return {
        "total_students": total_students,
        "pending_registrations": pending_registrations,
        "active_enrollments": active_enrollments,
        "pending_fee_records": pending_fee_records,
        "recent_registrations": recent_registrations,
    }


# ========================================
# Registration Requests
# ========================================
@router.get("/registration-requests", response_model=List[dict])
async def list_registration_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    query = select(RegistrationRequest)
    
    if status_filter:
        query = query.where(RegistrationRequest.status == status_filter)
    
    query = query.order_by(RegistrationRequest.submitted_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    requests = result.scalars().all()
    
    return [
        {
            "id": str(r.id),
            "request_id": r.request_id,
            "full_name": r.full_name,
            "email": r.email,
            "mobile": r.mobile,
            "date_of_birth": r.date_of_birth.isoformat() if r.date_of_birth else None,
            "is_minor": r.is_minor,
            "address": r.address,
            "guardian_name": r.guardian_name,
            "guardian_relationship": r.guardian_relationship,
            "guardian_email": r.guardian_email,
            "guardian_mobile": r.guardian_mobile,
            "selected_programmes": r.selected_programmes,
            "status": r.status,
            "review_notes": r.review_notes,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
            "review_deadline": r.review_deadline.isoformat() if r.review_deadline else None,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
        }
        for r in requests
    ]


@router.get("/registration-requests/{request_id}")
async def get_registration_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    result = await db.execute(
        select(RegistrationRequest).where(RegistrationRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    
    if not req:
        raise HTTPException(status_code=404, detail="Registration request not found")
    
    return {
        "id": str(req.id),
        "request_id": req.request_id,
        "full_name": req.full_name,
        "email": req.email,
        "mobile": req.mobile,
        "date_of_birth": req.date_of_birth.isoformat() if req.date_of_birth else None,
        "is_minor": req.is_minor,
        "address": req.address,
        "guardian_name": req.guardian_name,
        "guardian_relationship": req.guardian_relationship,
        "guardian_email": req.guardian_email,
        "guardian_mobile": req.guardian_mobile,
        "selected_programmes": req.selected_programmes,
        "status": req.status,
        "review_notes": req.review_notes,
        "submitted_at": req.submitted_at.isoformat() if req.submitted_at else None,
        "review_deadline": req.review_deadline.isoformat() if req.review_deadline else None,
        "reviewed_at": req.reviewed_at.isoformat() if req.reviewed_at else None,
        "reviewed_by": str(req.reviewed_by) if req.reviewed_by else None,
    }


def _slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80] or "student"


async def _unique_portal_slug(db: AsyncSession, base: str) -> str:
    slug = _slugify(base)
    candidate = slug
    suffix = 2
    while True:
        existing = await db.execute(select(Student).where(Student.portal_slug == candidate))
        if not existing.scalar_one_or_none():
            return candidate
        candidate = f"{slug}-{suffix}"
        suffix += 1


async def _approve_registration(
    db: AsyncSession,
    req: RegistrationRequest,
    current_user: User,
    notes: str,
) -> dict:
    """Approve an application WITHOUT creating any account.

    Private-academy policy: student accounts, enrolments and temporary
    credentials are only ever created by a separate, explicit admin action
    (see POST /registration-requests/{id}/provision) — never merely because
    an application exists.
    """
    if req.status == RegistrationRequestStatus.APPROVED and req.student_id:
        student = (await db.execute(select(Student).where(Student.id == req.student_id))).scalar_one_or_none()
        if student:
            return {
                "message": "Registration already approved",
                "status": "approved",
                "account_created": False,
                "student_id": str(student.id),
                "cma_registration_id": student.cma_registration_id,
            }

    before = req.status
    req.status = RegistrationRequestStatus.APPROVED
    req.reviewed_by = current_user.id
    req.reviewed_at = datetime.utcnow()
    req.review_notes = notes or "Approved"
    db.add(req)
    await db.flush()

    await record_audit(
        db,
        action="registration.approved",
        entity_type="registration_request",
        entity_id=req.request_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Approved application {req.request_id} for {req.full_name} (no account created yet)",
        before_data={"status": before},
        after_data={"status": RegistrationRequestStatus.APPROVED},
    )
    await db.flush()
    return {
        "message": ("Application approved. Create the student account explicitly "
                    "with 'Provision Student' (a temporary PIN is issued there)."),
        "status": "approved",
        "account_created": False,
        "request_id": req.request_id,
        "full_name": req.full_name,
        "email": req.email,
        "mobile": req.mobile,
        "selected_programmes": req.selected_programmes or [],
    }


@router.patch("/registration-requests/{request_id}/status")
async def update_registration_status(
    request_id: UUID,
    status_update: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    result = await db.execute(
        select(RegistrationRequest).where(RegistrationRequest.id == request_id)
    )
    req = result.scalar_one_or_none()
    
    if not req:
        raise HTTPException(status_code=404, detail="Registration request not found")
    
    new_status = status_update.get("status")
    if new_status not in ["approved", "rejected", "needs_information", "pending_review"]:
        raise HTTPException(status_code=400, detail="Invalid status")

    notes = (status_update.get("notes") or "").strip()

    if new_status == "approved":
        return await _approve_registration(db, req, current_user, notes)

    # Rejection / information request — no student identity is created
    if new_status == "rejected" and not notes:
        raise HTTPException(status_code=400, detail="A reason is required when closing an application")

    before_status = req.status
    req.status = new_status
    req.reviewed_by = current_user.id
    req.reviewed_at = datetime.utcnow()
    req.review_notes = notes
    await db.flush()

    await record_audit(
        db,
        action=f"registration.{new_status}",
        entity_type="registration_request",
        entity_id=req.request_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=notes or f"Status changed to {new_status}",
        before_data={"status": before_status},
        after_data={"status": new_status, "notes": notes},
        ip_address=request.client.host if request.client else None,
    )

    label = {
        "rejected": "Closed",
        "needs_information": "Additional information requested",
        "pending_review": "Pending review",
    }.get(new_status, new_status)

    try:
        email_service.send_registration_closed(
            to_email=req.email,
            full_name=req.full_name,
            status_label=label,
            reason=notes,
        )
    except Exception:
        pass

    return {"message": f"Registration request {new_status}", "status": new_status}


# ========================================
# Students
# ========================================
@router.get("/students")
async def list_students(
    skip: int = 0,
    limit: int = 50,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    query = select(Student, User.email, User.username, func.count(Enrollment.id)).outerjoin(
        User, User.id == Student.user_id
    ).outerjoin(Enrollment, Enrollment.student_id == Student.id)

    if search:
        query = query.where(
            Student.first_name.ilike(f"%{search}%") |
            Student.last_name.ilike(f"%{search}%") |
            Student.cma_registration_id.ilike(f"%{search}%") |
            User.username.ilike(f"%{search}%")
        )

    query = (
        query.group_by(Student.id, User.email, User.username)
        .order_by(Student.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)

    return [
        {
            "id": str(student.id),
            "cma_registration_id": student.cma_registration_id,
            "login_id": username,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "full_name": student.full_name,
            "email": email,
            "phone": student.phone,
            "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
            "status": student.status,
            "skill_level": student.skill_level,
            "profile_complete": student.profile_complete,
            "enrollment_count": enrollment_count,
            "created_at": student.created_at.isoformat() if student.created_at else None,
        }
        for student, email, username, enrollment_count in result.all()
    ]


@router.get("/students/{student_id}")
async def get_student_detail(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    # Account identity + security status
    user = (await db.execute(select(User).where(User.id == student.user_id))).scalar_one_or_none()
    login_id = user.username if user else None
    login_email = user.email if user else None
    must_change_pin = bool(user.must_change_pin) if user else None
    
    # Get enrollments (with assigned instructor names)
    enrollments_result = await db.execute(
        select(Enrollment).where(Enrollment.student_id == student_id)
    )
    enrollments = enrollments_result.scalars().all()
    instructor_names = {}
    if enrollments:
        ids = {e.instructor_id for e in enrollments if e.instructor_id}
        if ids:
            irows = (await db.execute(select(Instructor).where(Instructor.id.in_(ids)))).scalars().all()
            instructor_names = {i.id: f"{i.first_name} {i.last_name}" for i in irows}

    guardians_result = await db.execute(
        select(Guardian).where(Guardian.student_id == student_id)
    )
    guardians = guardians_result.scalars().all()

    return {
        "id": str(student.id),
        "cma_registration_id": student.cma_registration_id,
        "first_name": student.first_name,
        "last_name": student.last_name,
        "full_name": student.full_name,
        "phone": student.phone,
        "date_of_birth": student.date_of_birth.isoformat() if student.date_of_birth else None,
        "address": student.address,
        "status": student.status,
        "skill_level": student.skill_level,
        "profile_complete": student.profile_complete,
        "guardians": [
            {
                "id": str(g.id),
                "first_name": g.first_name,
                "last_name": g.last_name,
                "relationship": g.guardian_relationship,
                "phone": g.phone,
                "email": g.email,
            }
            for g in guardians
        ],
        "login_id": login_id,
        "email": login_email,
        "must_change_pin": must_change_pin,
        "enrollments": [
            {
                "id": str(e.id),
                "programme_id": e.programme_id,
                "programme_name": e.programme_name,
                "status": e.status,
                "fee_plan": e.fee_plan,
                "fee_amount": float(e.fee_amount) if e.fee_amount else None,
                "instructor_id": str(e.instructor_id) if e.instructor_id else None,
                "instructor_name": instructor_names.get(e.instructor_id),
                "start_date": e.start_date.isoformat() if e.start_date else None,
            }
            for e in enrollments
        ],
        "created_at": student.created_at.isoformat() if student.created_at else None,
    }


# ========================================
# Enrollments
# ========================================
@router.get("/enrollments")
async def list_enrollments(
    skip: int = 0,
    limit: int = 50,
    student_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    query = (
        select(Enrollment, Student, Instructor)
        .join(Student, Student.id == Enrollment.student_id)
        .outerjoin(Instructor, Instructor.id == Enrollment.instructor_id)
    )

    if student_id:
        query = query.where(Enrollment.student_id == student_id)
    if status_filter:
        query = query.where(Enrollment.status == status_filter)

    query = query.order_by(Enrollment.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)

    return [
        {
            "id": str(enrollment.id),
            "student_id": str(student.id),
            "student_name": student.full_name,
            "cma_registration_id": student.cma_registration_id,
            "programme_id": enrollment.programme_id,
            "programme_name": enrollment.programme_name,
            "instructor_id": str(enrollment.instructor_id) if enrollment.instructor_id else None,
            "instructor": (
                f"{instructor.first_name} {instructor.last_name}" if instructor else None
            ),
            "fee_plan": enrollment.fee_plan,
            "fee_amount": float(enrollment.fee_amount) if enrollment.fee_amount else None,
            "status": enrollment.status,
            "start_date": enrollment.start_date.isoformat() if enrollment.start_date else None,
            "created_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
        }
        for enrollment, student, instructor in result.all()
    ]


@router.post("/enrollments")
async def create_enrollment(
    enrollment_data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    enrollment = Enrollment(
        student_id=enrollment_data["student_id"],
        programme_id=enrollment_data["programme_id"],
        programme_name=enrollment_data["programme_name"],
        instructor_id=enrollment_data.get("instructor_id"),
        fee_plan=enrollment_data.get("fee_plan"),
        fee_amount=enrollment_data.get("fee_amount"),
        status=EnrollmentStatus.ACTIVE,
        start_date=date.today(),
    )
    db.add(enrollment)
    await db.flush()
    
    return {"id": str(enrollment.id), "message": "Enrollment created"}


# ========================================
# Instructors
# ========================================
@router.get("/instructors")
async def list_instructors(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    result = await db.execute(select(Instructor))
    instructors = result.scalars().all()
    
    return [
        {
            "id": str(i.id),
            "first_name": i.first_name,
            "last_name": i.last_name,
            "full_name": f"{i.first_name} {i.last_name}",
            "phone": i.phone,
            "specializations": i.specializations,
            "qualifications": i.qualifications,
            "experience_years": i.experience_years,
            "is_active": i.is_active,
        }
        for i in instructors
    ]


# ========================================
# Fee Records
# ========================================
@router.get("/fees")
async def list_fee_records(
    skip: int = 0,
    limit: int = 50,
    student_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    query = (
        select(FeeRecord, Student)
        .join(Student, Student.id == FeeRecord.student_id)
    )

    if student_id:
        query = query.where(FeeRecord.student_id == student_id)
    if status_filter:
        query = query.where(FeeRecord.payment_status == status_filter)

    query = query.order_by(FeeRecord.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)

    return [
        {
            "id": str(fee.id),
            "enrollment_id": str(fee.enrollment_id),
            "student_id": str(student.id),
            "student_name": student.full_name,
            "cma_registration_id": student.cma_registration_id,
            "fee_plan": fee.fee_plan,
            "period": fee.period,
            "amount_expected": float(fee.amount_expected),
            "amount_paid": float(fee.amount_paid),
            "payment_status": fee.payment_status,
            "payment_date": fee.payment_date.isoformat() if fee.payment_date else None,
            "payment_method": fee.payment_method,
            "transaction_ref": fee.transaction_ref,
            "is_complimentary": fee.is_complimentary,
            "created_at": fee.created_at.isoformat() if fee.created_at else None,
        }
        for fee, student in result.all()
    ]


# ========================================
# Student progress (syllabus + reports overview)
# ========================================
@router.get("/progress")
async def student_progress_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """
    Academy-wide progress overview: real syllabus completion, latest published
    report and pending assignments per student. Nothing is cached or estimated.
    """
    from app.models.learning import Assignment, Submission
    from app.models.reports import MonthlyReport
    from app.models.syllabus import StudentSyllabusProgress
    from app.models.notification import Notification  # keep import surface stable

    students_result = await db.execute(
        select(Student).where(Student.status == "active").order_by(Student.created_at.asc())
    )
    students = list(students_result.scalars().all())
    if not students:
        return {"students": []}
    student_ids = [s.id for s in students]

    progress_rows = await db.execute(
        select(StudentSyllabusProgress).where(StudentSyllabusProgress.student_id.in_(student_ids))
    )
    syllabus_by_student: dict = {}
    for p in progress_rows.scalars().all():
        entry = syllabus_by_student.setdefault(p.student_id, {"completed": 0, "total": 0})
        entry["total"] += 1
        if p.status == "completed":
            entry["completed"] += 1

    report_rows = await db.execute(
        select(MonthlyReport)
        .where(MonthlyReport.student_id.in_(student_ids))
        .order_by(MonthlyReport.report_month.desc(), MonthlyReport.revision.desc())
    )
    latest_report: dict = {}
    for r in report_rows.scalars().all():
        latest_report.setdefault(
            r.student_id,
            {"report_month": r.report_month, "status": r.status, "id": str(r.id)},
        )

    pending_rows = await db.execute(
        select(Assignment.student_id, func.count(Assignment.id))
        .where(
            Assignment.student_id.in_(student_ids),
            Assignment.status.in_(["assigned", "revision_requested"]),
        )
        .group_by(Assignment.student_id)
    )
    pending = dict(pending_rows.all())

    rows = []
    for s in students:
        syllabus = syllabus_by_student.get(s.id, {"completed": 0, "total": 0})
        total = syllabus["total"]
        rows.append(
            {
                "student_id": str(s.id),
                "student_name": s.full_name,
                "cma_registration_id": s.cma_registration_id,
                "syllabus_completed": syllabus["completed"],
                "syllabus_total": total,
                "syllabus_percent": round((syllabus["completed"] / total) * 100) if total else None,
                "latest_report": latest_report.get(s.id),
                "pending_assignments": pending.get(s.id, 0),
            }
        )
    return {"students": rows}


# ========================================
# Audit trail
# ========================================
@router.get("/audit")
async def list_audit_events(
    action_prefix: Optional[str] = None,
    entity_type: Optional[str] = None,
    actor_user_id: Optional[UUID] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    from app.models.audit import AuditEvent

    query = select(AuditEvent, User.email).outerjoin(User, User.id == AuditEvent.actor_user_id)
    if action_prefix:
        query = query.where(AuditEvent.action.like(f"{action_prefix}%"))
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if actor_user_id:
        query = query.where(AuditEvent.actor_user_id == actor_user_id)

    query = query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    return [
        {
            "id": str(event.id),
            "action": event.action,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "summary": event.summary,
            "actor_role": event.actor_role,
            "actor_email": email,
            "before_data": event.before_data,
            "after_data": event.after_data,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        }
        for event, email in result.all()
    ]


# ========================================
# Operational settings (read-only, non-secret)
# ========================================
@router.get("/settings")
async def operational_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """
    Effective operational configuration for the admin console.

    Secrets (passwords, keys, webhook secrets, access keys) are NEVER returned —
    only whether an integration is configured and in which mode.
    """
    from app.models.billing import FeePackage
    from app.services.payments import razorpay_service

    packages_result = await db.execute(
        select(FeePackage).where(FeePackage.is_active.is_(True)).order_by(FeePackage.fee_paise.asc())
    )
    packages = [
        {
            "id": str(p.id),
            "code": p.code,
            "name": p.name,
            "sessions_included": p.sessions_included,
            "fee_paise": p.fee_paise,
            "session_duration_minutes": p.session_duration_minutes,
            "is_legacy": p.is_legacy,
        }
        for p in packages_result.scalars().all()
    ]

    return {
        "timezone": settings.TIMEZONE,
        "currency": settings.CURRENCY,
        "rate_limit_enabled": settings.RATE_LIMIT_ENABLED,
        "email_test_mode": settings.EMAIL_TEST_MODE,
        "web3forms_configured": bool(settings.WEB3FORMS_ACCESS_KEY),
        "razorpay": razorpay_service.public_config(),
        "max_upload_mb": settings.MAX_UPLOAD_MB,
        "seed_demo_data": settings.SEED_DEMO_DATA,
        "fee_packages": packages,
    }


# ========================================
# Weekly Timetable (authoritative schedules)
# ========================================
@router.get("/schedules")
async def list_weekly_schedules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Authoritative weekly timetable with overlap conflict detection.

    Conflict warnings are returned, never auto-resolved — the timetable is
    never silently altered.
    """
    rows = await db.execute(
        select(ClassSchedule, Enrollment, Student, User.username, Instructor)
        .join(Enrollment, Enrollment.id == ClassSchedule.enrollment_id)
        .join(Student, Student.id == Enrollment.student_id)
        .join(User, User.id == Student.user_id)
        .outerjoin(Instructor, Instructor.id == ClassSchedule.instructor_id)
    )

    day_order = {d: i for i, d in enumerate(
        ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    )}

    schedules = []
    for cs, enr, stu, login_id, instr in rows.all():
        schedules.append({
            "id": str(cs.id),
            "enrollment_id": str(enr.id),
            "student_id": str(stu.id),
            "student_name": stu.full_name,
            "login_id": login_id,
            "instrument": enr.programme_name,
            "day_of_week": cs.day_of_week,
            "start_time": cs.start_time.isoformat() if cs.start_time else None,
            "end_time": cs.end_time.isoformat() if cs.end_time else None,
            "frequency": cs.frequency or "weekly",
            "is_active": bool(cs.is_active) if cs.is_active is not None else True,
            "start_date": cs.start_date.isoformat() if cs.start_date else None,
            "instructor_id": str(cs.instructor_id) if cs.instructor_id else None,
            "instructor_name": (
                f"{instr.first_name} {instr.last_name}".strip() if instr else None
            ),
        })

    schedules.sort(key=lambda s: (
        day_order.get(s["day_of_week"], 99),
        s["start_time"] or "",
    ))

    # Overlap detection (active weekly entries, same day)
    conflicts = []
    active = [s for s in schedules if s["is_active"] and s["start_time"] and s["end_time"]]
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            a, b = active[i], active[j]
            if a["day_of_week"] != b["day_of_week"]:
                continue
            if a["start_time"] < b["end_time"] and b["start_time"] < a["end_time"]:
                conflicts.append({
                    "day_of_week": a["day_of_week"],
                    "student_a": a["student_name"],
                    "student_b": b["student_name"],
                    "overlap_start": max(a["start_time"], b["start_time"]),
                    "overlap_end": min(a["end_time"], b["end_time"]),
                    "auto_resolved": False,
                })

    missing_instructor = [s["login_id"] for s in schedules if not s["instructor_id"]]

    return {
        "schedules": schedules,
        "conflicts": conflicts,
        "missing_instructor": missing_instructor,
    }


# ========================================
# Student PIN reset (administrator)
# ========================================
@router.post("/students/{student_id}/reset-pin")
async def reset_student_pin(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    """Generate a new temporary 4-digit PIN for a student.

    The PIN is returned ONCE to the administrator here, stored only as a
    hash, and forces a change on the student's next login.
    """
    import secrets

    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    user_result = await db.execute(select(User).where(User.id == student.user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Student user account not found")

    new_pin = f"{secrets.randbelow(10000):04d}"
    user.hashed_password = get_password_hash(new_pin)
    user.must_change_pin = True
    db.add(user)
    await db.flush()

    await record_audit(
        db,
        action="student.pin_reset",
        entity_type="student",
        entity_id=student.id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"PIN reset for {student.full_name} ({user.username})",
    )

    return {
        "student_id": str(student.id),
        "login_id": user.username,
        "new_pin": new_pin,  # shown once to the administrator only
        "must_change_pin": True,
    }


# ========================================
# PIN reset requests (admin-managed Forgot PIN)
# ========================================
@router.get("/pin-reset-requests")
async def list_pin_reset_requests(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    query = select(PinResetRequest).order_by(PinResetRequest.created_at.desc())
    if status_filter:
        query = query.where(PinResetRequest.status == status_filter)
    rows = (await db.execute(query)).scalars().all()

    out = []
    for r in rows:
        login_id = None
        display_name = None
        if r.resolved_user_id:
            user = (await db.execute(select(User).where(User.id == r.resolved_user_id))).scalar_one_or_none()
            if user:
                login_id = user.username
                student = (await db.execute(select(Student).where(Student.user_id == user.id))).scalar_one_or_none()
                if student:
                    display_name = student.full_name
                else:
                    instructor = (await db.execute(select(Instructor).where(Instructor.user_id == user.id))).scalar_one_or_none()
                    display_name = f"{instructor.first_name} {instructor.last_name}" if instructor else None
        out.append({
            "id": str(r.id),
            "request_id": r.request_id,
            "username_submitted": r.username_submitted,
            "account_login_id": login_id,
            "account_name": display_name,
            "contact": r.contact,
            "details": r.details,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "review_notes": r.review_notes,
        })
    return out


def _gen_temp_pin() -> str:
    return f"{secrets.randbelow(10000):04d}"


@router.post("/pin-reset-requests/{request_id}/approve")
async def approve_pin_reset(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Issue a new temporary PIN for the requester's account.

    The plaintext PIN is returned exactly once, to this admin response only.
    It is stored exclusively as a hash; must_change_pin is forced true.
    """
    req = (await db.execute(select(PinResetRequest).where(PinResetRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="PIN reset request not found")
    if req.status != PinResetRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"This request is already {req.status}")

    user = None
    if req.resolved_user_id:
        user = (await db.execute(select(User).where(User.id == req.resolved_user_id))).scalar_one_or_none()
    if user is None:
        user = (await db.execute(select(User).where(User.username == req.username_submitted))).scalar_one_or_none()
    if user is None:
        req.status = PinResetRequestStatus.REJECTED
        req.review_notes = "No matching account found for the submitted login id"
        req.reviewed_by = current_user.id
        req.reviewed_at = datetime.utcnow()
        db.add(req)
        await db.flush()
        raise HTTPException(status_code=404, detail="No account matches the submitted login id")

    new_pin = _gen_temp_pin()
    user.hashed_password = get_password_hash(new_pin)
    user.must_change_pin = True
    db.add(user)

    req.status = PinResetRequestStatus.APPROVED
    req.reviewed_by = current_user.id
    req.reviewed_at = datetime.utcnow()
    req.resolved_user_id = user.id
    db.add(req)
    await db.flush()

    await record_audit(
        db,
        action="pin_reset.approved",
        entity_type="pin_reset_request",
        entity_id=str(req.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Temporary PIN issued for {user.username} ({req.request_id})",
    )
    await notify_user(
        db,
        user_id=user.id,
        type="pin_reset",
        title="Temporary PIN issued",
        body="A temporary PIN has been issued. You must choose a new PIN at your next sign-in.",
        dedupe_key=f"pinreset:{req.request_id}",
        related_entity_type="pin_reset_request",
        related_entity_id=str(req.id),
    )
    await db.flush()

    return {
        "request_id": req.request_id,
        "login_id": user.username,
        "new_pin": new_pin,          # shown to the admin exactly once
        "must_change_pin": True,
    }


@router.post("/pin-reset-requests/{request_id}/reject")
async def reject_pin_reset(
    request_id: UUID,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    notes = (payload.get("notes") or "").strip()
    if not notes:
        raise HTTPException(status_code=400, detail="A reason is required when rejecting a request")
    req = (await db.execute(select(PinResetRequest).where(PinResetRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="PIN reset request not found")
    if req.status != PinResetRequestStatus.PENDING:
        raise HTTPException(status_code=400, detail=f"This request is already {req.status}")
    req.status = PinResetRequestStatus.REJECTED
    req.review_notes = notes
    req.reviewed_by = current_user.id
    req.reviewed_at = datetime.utcnow()
    db.add(req)
    await db.flush()
    await record_audit(
        db,
        action="pin_reset.rejected",
        entity_type="pin_reset_request",
        entity_id=str(req.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Rejected {req.request_id}: {notes}",
    )
    return {"id": str(req.id), "status": req.status}


# ========================================
# Student account management (admin CRUD)
# ========================================
class AdminStudentCreate(BaseModel):
    username: str
    first_name: str
    last_name: str = ""
    cma_registration_id: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    skill_level: Optional[str] = None
    programme_id: Optional[str] = None
    programme_name: Optional[str] = None
    fee_plan: Optional[str] = None
    fee_amount: Optional[float] = None
    instructor_id: Optional[UUID] = None


class AdminStudentUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    skill_level: Optional[str] = None
    status: Optional[str] = None          # active | suspended | archived
    notes: Optional[str] = None


_USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,100}$")
_ALLOWED_STUDENT_STATUS = {"active", "suspended", "archived"}
_ALLOWED_FEE_PLANS = {"4_classes", "8_classes", "per_class"}


async def _unique_username_exists(db: AsyncSession, username: str, exclude_user_id: UUID = None) -> bool:
    q = select(User).where(User.username == username)
    if exclude_user_id:
        q = q.where(User.id != exclude_user_id)
    return (await db.execute(q)).scalar_one_or_none() is not None


@router.post("/students", status_code=status.HTTP_201_CREATED)
async def admin_create_student(
    body: AdminStudentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Create a student account with a secure temporary PIN (shown once)."""
    username = body.username.strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="Login ID must be 3-100 chars (letters, digits, . _ -)")
    if not body.first_name.strip():
        raise HTTPException(status_code=400, detail="First name is required")
    if await _unique_username_exists(db, username):
        raise HTTPException(status_code=409, detail="That login ID is already in use")
    if body.email:
        email_row = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
        if email_row:
            raise HTTPException(status_code=409, detail="That email is already in use")
    if body.fee_plan and body.fee_plan not in _ALLOWED_FEE_PLANS:
        raise HTTPException(status_code=400, detail="fee_plan must be 4_classes or 8_classes")

    dob = None
    if body.date_of_birth:
        try:
            dob = date.fromisoformat(body.date_of_birth)
        except ValueError:
            raise HTTPException(status_code=400, detail="date_of_birth must be YYYY-MM-DD")

    cma_id = body.cma_registration_id or await CMAIdService.generate_cma_id(db)
    if body.cma_registration_id:
        clash = (await db.execute(select(Student).where(Student.cma_registration_id == cma_id))).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="That CMA Roll Number is already in use")

    temp_pin = _gen_temp_pin()
    user = User(
        email=body.email.lower() if body.email else None,
        username=username,
        hashed_password=get_password_hash(temp_pin),
        role=UserRole.STUDENT,
        is_active=True,
        must_change_pin=True,
    )
    db.add(user)
    await db.flush()

    slug = re.sub(r"[^a-z0-9]+", "-", body.first_name.strip().lower()).strip("-")
    base_slug, n = slug or "student", 1
    while (await db.execute(select(Student).where(Student.portal_slug == slug))).scalar_one_or_none():
        n += 1
        slug = f"{base_slug}-{n}"

    student = Student(
        user_id=user.id,
        cma_registration_id=cma_id,
        portal_slug=slug,
        first_name=body.first_name.strip(),
        last_name=(body.last_name or "").strip(),
        date_of_birth=dob,
        phone=(body.phone or "").strip() or None,
        status="active",
        skill_level=body.skill_level,
        profile_complete=False,
        notes="Created by administrator",
    )
    db.add(student)
    await db.flush()

    enrollment = None
    if body.programme_id:
        enrollment = Enrollment(
            student_id=student.id,
            programme_id=body.programme_id.strip(),
            programme_name=(body.programme_name or body.programme_id).strip(),
            instructor_id=body.instructor_id,
            fee_plan=body.fee_plan,
            fee_amount=body.fee_amount,
            status="active",
            start_date=date.today(),
        )
        db.add(enrollment)
        await db.flush()

    await record_audit(
        db,
        action="student.created",
        entity_type="student",
        entity_id=str(student.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Created student {student.full_name} ({cma_id}, login {username})",
    )
    await db.flush()

    return {
        "id": str(student.id),
        "cma_registration_id": cma_id,
        "login_id": username,
        "full_name": student.full_name,
        "temp_pin": temp_pin,               # shown to admin exactly once
        "must_change_pin": True,
        "enrollment_id": str(enrollment.id) if enrollment else None,
    }


@router.patch("/students/{student_id}")
async def admin_update_student(
    student_id: UUID,
    body: AdminStudentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    before = {"status": student.status, "phone": student.phone, "skill_level": student.skill_level}

    if body.first_name is not None and body.first_name.strip():
        student.first_name = body.first_name.strip()
    if body.last_name is not None:
        student.last_name = body.last_name.strip()
    if body.phone is not None:
        student.phone = body.phone.strip() or None
    if body.skill_level is not None:
        student.skill_level = body.skill_level
    if body.notes is not None:
        student.notes = body.notes
    if body.date_of_birth is not None:
        try:
            student.date_of_birth = date.fromisoformat(body.date_of_birth)
        except ValueError:
            raise HTTPException(status_code=400, detail="date_of_birth must be YYYY-MM-DD")
    if body.status is not None:
        if body.status not in _ALLOWED_STUDENT_STATUS:
            raise HTTPException(status_code=400, detail="status must be active, suspended or archived")
        student.status = body.status
        # keep sign-in in sync: suspended/archived students must not be able to log in
        user = (await db.execute(select(User).where(User.id == student.user_id))).scalar_one()
        user.is_active = (body.status == "active")
        db.add(user)
    if body.email is not None:
        user = (await db.execute(select(User).where(User.id == student.user_id))).scalar_one()
        if body.email.lower() != (user.email or ""):
            dup = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
            if dup:
                raise HTTPException(status_code=409, detail="That email is already in use")
            user.email = body.email.lower()
            db.add(user)

    student.profile_complete = bool(
        student.first_name and student.last_name and student.date_of_birth
    )
    db.add(student)
    await db.flush()
    await record_audit(
        db,
        action="student.updated",
        entity_type="student",
        entity_id=str(student.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        before_data=before,
        after_data={"status": student.status, "phone": student.phone, "skill_level": student.skill_level},
    )
    result = await db.execute(select(Student).where(Student.id == student.id))
    s = result.scalar_one()
    return {"id": str(s.id), "full_name": s.full_name, "status": s.status,
            "cma_registration_id": s.cma_registration_id, "phone": s.phone}


# ========================================
# Student permanent deletion (schema-aware, transactional)
# ========================================
# Explicit cleanup map: table -> {column: scope-key}.  Columns that are not
# present on a table are ignored, so the map is safe across schema eras.
# Children are listed before parents (topological: files→submissions→assignments,
# history→sessions, schedules→enrollments, … → students → users).
_STUDENT_REMOVE_MAP: list[tuple[str, dict[str, str]]] = [
    ("assignment_files", {"assignment_id": "assignments", "owner_user_id": "users"}),
    ("submissions", {"student_id": "student", "assignment_id": "assignments", "enrollment_id": "enrollments"}),
    ("assignments", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("session_status_history", {"session_id": "sessions"}),
    ("class_sessions", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("attendance", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("class_schedules", {"enrollment_id": "enrollments"}),
    ("progress", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("milestones", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("monthly_reports", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("student_syllabus_progress", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("student_syllabus_assignments", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("student_instruments", {"student_id": "student"}),
    ("student_remarks", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("achievements", {"student_id": "student"}),
    ("material_assignments", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("resource_visibility_targets", {"student_id": "student"}),
    ("exam_items", {"exam_id": "exams"}),
    ("exams", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("guardians", {"student_id": "student"}),
    ("guardian_accounts", {"student_id": "student"}),
    ("notifications", {"user_id": "users"}),
    ("pin_reset_requests", {"user_id": "users"}),
    ("email_verification_tokens", {"user_id": "users"}),
    ("support_replies", {"author_user_id": "users"}),
    ("enrollments", {"student_id": "student"}),
]

# Financial + audit/application rows are RETAINED: their student/enrollment
# links are released (SET NULL) inside the same transaction before the
# student/enrollment rows disappear.  This is the documented retention
# strategy — invoice/payment/fee integrity is preserved, unique identifiers
# (username, CMA registration id) are freed for reuse.
_STUDENT_RETAIN_UNLINK: list[tuple[str, dict[str, str]]] = [
    ("invoices", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("fee_records", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("payment_allocations", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("credit_ledger", {"student_id": "student", "enrollment_id": "enrollments"}),
    ("exam_fees", {"student_id": "student", "enrollment_id": "enrollments"}),
    # application / support history keeps existing but drops the link:
    ("registration_requests", {"student_id": "student"}),
    ("support_requests", {"related_student_id": "student", "related_enrollment_id": "enrollments", "related_session_id": "sessions"}),
    # defensive NO ACTION FKs (prod-era constraints) — never a deletion blocker:
    ("audit_events", {"actor_user_id": "users"}),
    ("payments", {"payer_user_id": "users"}),
]


async def _collect_student_scopes(db: AsyncSession, student) -> dict:
    uid = student.id
    enr = [r[0] for r in (await db.execute(select(Enrollment.id).where(Enrollment.student_id == uid))).all()]
    sess = [r[0] for r in (await db.execute(select(ClassSession.id).where(ClassSession.student_id == uid))).all()]
    asg_q = select(Assignment.id).where(
        or_(Assignment.student_id == uid, Assignment.enrollment_id.in_(enr)) if enr
        else Assignment.student_id == uid
    )
    asg = [r[0] for r in (await db.execute(asg_q)).all()]
    from app.models.exam import Exam
    exam_q = select(Exam.id).where(
        or_(Exam.student_id == uid, Exam.enrollment_id.in_(enr)) if enr
        else Exam.student_id == uid
    )
    exams = [r[0] for r in (await db.execute(exam_q)).all()]
    # guardian (parent) accounts belonging to this student
    ga_t = Base.metadata.tables.get("guardian_accounts")
    parent_users: list[UUID] = []
    if ga_t is not None:
        rows = (await db.execute(
            select(ga_t.c.user_id).where(ga_t.c.student_id == uid)
        )).all()
        parent_users = [r[0] for r in rows]
    # a parent user is deleted with the student only when no other student
    # still depends on that account (siblings keep their guardian login)
    deleting_parents: list[UUID] = []
    for p in parent_users:
        others = (await db.execute(
            select(func.count()).select_from(ga_t)
            .where(ga_t.c.user_id == p, ga_t.c.student_id != uid)
        )).scalar() if ga_t is not None else 0
        if not others:
            deleting_parents.append(p)
    return {
        "student": uid,
        "enrollments": enr,
        "sessions": sess,
        "assignments": asg,
        "exams": exams,
        "users": [student.user_id, *deleting_parents],  # student login + orphaned parent logins
        "parents_deleting": deleting_parents,
    }


def _scope_clause_for(table, map_entry: dict[str, str], scopes: dict):
    clauses = []
    for col_name, key in map_entry.items():
        if col_name not in table.c:
            continue
        val = scopes.get(key)
        if val is None:
            continue
        if isinstance(val, (list, tuple, set)):
            if not val:
                continue
            clauses.append(table.c[col_name].in_(list(val)))
        else:
            clauses.append(table.c[col_name] == val)
    if not clauses:
        return None
    return or_(*clauses) if len(clauses) > 1 else clauses[0]


async def _student_delete_impact(db: AsyncSession, student, scopes: dict) -> dict:
    remove: dict[str, int] = {}
    for tname, mmap in _STUDENT_REMOVE_MAP:
        t = Base.metadata.tables.get(tname)
        if t is None:
            continue
        clause = _scope_clause_for(t, mmap, scopes)
        remove[tname] = 0 if clause is None else int(
            (await db.execute(select(func.count()).select_from(t).where(clause))).scalar() or 0
        )
    retain: dict[str, int] = {}
    for tname, mmap in _STUDENT_RETAIN_UNLINK:
        t = Base.metadata.tables.get(tname)
        if t is None:
            continue
        clause = _scope_clause_for(t, mmap, scopes)
        retain[tname] = 0 if clause is None else int(
            (await db.execute(select(func.count()).select_from(t).where(clause))).scalar() or 0
        )
    academic = {k: v for k, v in remove.items() if k not in ("notifications", "pin_reset_requests", "email_verification_tokens", "support_replies", "guardian_accounts", "guardians")}
    financial = {k: v for k, v in retain.items() if k in ("invoices", "fee_records", "payment_allocations", "credit_ledger", "exam_fees")}
    archive_recommended = any(academic.values())
    warnings = []
    if archive_recommended:
        warnings.append("This student has academic history — archiving is RECOMMENDED because it preserves everything without deletion.")
    if any(financial.values()):
        warnings.append("Financial records exist: they will be RETAINED for accounting with their student/enrollment link released (cannot be viewed under this student anymore).")
    if remove.get("guardian_accounts"):
        warnings.append(f"{remove['guardian_accounts']} guardian login(s) used only by this student will also be removed.")
    warnings.append("Permanent deletion is irreversible: the login username and CMA registration ID become available for reuse.")
    return {
        "student": {"id": str(student.id), "full_name": student.full_name,
                    "cma_registration_id": student.cma_registration_id, "status": student.status},
        "remove": remove,
        "retain_unlinked": retain,
        "archive_recommended": archive_recommended,
        "warnings": warnings,
    }


@router.get("/students/{student_id}/delete-impact")
async def admin_student_delete_impact(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Report exactly what a permanent delete would remove vs retain."""
    student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    scopes = await _collect_student_scopes(db, student)
    return await _student_delete_impact(db, student, scopes)


@router.delete("/students/{student_id}")
async def admin_delete_student(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Permanently delete a student in one transaction.

    Archiving is never substituted silently: linked academic records are
    removed explicitly (children before parents), financial/audit records are
    retained with their student/enrollment link released, and the username +
    CMA registration ID are freed for reuse.  Any unresolved database
    dependency rolls the whole transaction back and is reported by name.
    """
    student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    released_username = None
    user_row = (await db.execute(select(User).where(User.id == student.user_id))).scalar_one_or_none()
    if user_row:
        released_username = user_row.username
    released_reg = student.cma_registration_id
    full_name = student.full_name

    scopes = await _collect_student_scopes(db, student)
    impact = await _student_delete_impact(db, student, scopes)

    try:
        # 1) retention: release links on financial/audit/application rows
        for tname, mmap in _STUDENT_RETAIN_UNLINK:
            t = Base.metadata.tables.get(tname)
            if t is None:
                continue
            clause = _scope_clause_for(t, mmap, scopes)
            if clause is None:
                continue
            for col_name in mmap:
                if col_name in t.c:
                    await db.execute(t.update().where(clause).values(**{col_name: None}))

        # 2) student-owned records: children before parents (explicit order)
        removed: dict[str, int] = {}
        for tname, mmap in _STUDENT_REMOVE_MAP:
            t = Base.metadata.tables.get(tname)
            if t is None:
                continue
            clause = _scope_clause_for(t, mmap, scopes)
            if clause is None:
                continue
            res = await db.execute(t.delete().where(clause))
            removed[tname] = int(res.rowcount or 0)

        # 3) students row then user accounts (student + orphaned parents)
        await db.execute(
            Student.__table__.delete().where(Student.__table__.c.id == student.id)
        )
        users_to_delete = list(scopes["users"])
        if users_to_delete:
            await db.execute(
                User.__table__.delete().where(User.__table__.c.id.in_(users_to_delete))
            )
        await db.flush()

        retained = impact["retain_unlinked"]
        await record_audit(
            db,
            action="student.deleted",
            entity_type="student",
            entity_id=str(student_id),
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            summary=(
                f"Permanently deleted student {full_name} "
                f"({released_reg}, login {released_username}); "
                f"removed academic rows, retained financial rows "
                f"(invoices={retained.get('invoices', 0)}, fee_records={retained.get('fee_records', 0)}); "
                f"identifiers released"
            ),
        )
    except (IntegrityError, DBAPIError) as e:
        await db.rollback()
        orig = getattr(getattr(e, "orig", None), "sqlstate", None) or str(e.orig or e)
        detail = str(orig)[:300]
        raise HTTPException(
            status_code=409,
            detail=f"Deletion rolled back — unresolvable database dependency: {detail}",
        )

    return {
        "deleted": True,
        "id": str(student_id),
        "released": {"username": released_username, "cma_registration_id": released_reg},
        "removed": impact["remove"],
        "retained_unlinked": impact["retain_unlinked"],
    }


# ========================================
# Monthly class scheduling (4 or 8 classes / month) with conflict detection
# ========================================
_MONTH_FMT = r"^\d{4}-\d{2}$"
_MONTH_NAMES = ["", "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"]


def _expected_classes(fee_plan: Optional[str]) -> Optional[int]:
    return {"4_classes": 4, "8_classes": 8}.get(fee_plan or "")


def _fmt12(t: dtime) -> str:
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {'AM' if t.hour < 12 else 'PM'}"


def _slot_overlaps(a_s: dtime, a_e: dtime, b_s: dtime, b_e: dtime) -> bool:
    # overlapping intervals (not merely identical start times)
    return a_s < b_e and a_e > b_s


async def _resolve_student_enrollment(db: AsyncSession, student, enrollment_id: Optional[UUID]) -> Enrollment:
    q = select(Enrollment).where(Enrollment.student_id == student.id)
    if enrollment_id:
        q = q.where(Enrollment.id == enrollment_id)
    else:
        q = q.where(Enrollment.status == "active")
    rows = (await db.execute(q.order_by(Enrollment.created_at.asc()))).scalars().all()
    if not rows:
        raise HTTPException(status_code=400,
                            detail="No active enrolment for this student — create or activate an enrolment first")
    if len(rows) > 1 and not enrollment_id:
        raise HTTPException(status_code=400,
                            detail="Student has multiple enrolments — choose which enrolment to schedule")
    return rows[0]


class MonthlyClassIn(BaseModel):
    date: str                 # YYYY-MM-DD
    start_time: str           # HH:MM
    end_time: str             # HH:MM
    instructor_id: Optional[UUID] = None


class MonthlyScheduleSave(BaseModel):
    month: str
    enrollment_id: Optional[UUID] = None
    instructor_id: Optional[UUID] = None
    classes: list[MonthlyClassIn]


@router.get("/students/{student_id}/monthly-schedule")
async def admin_monthly_schedule(
    student_id: UUID,
    month: str = Query(..., pattern=_MONTH_FMT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Review state for one month: plan expectation vs scheduled /
    completed / remaining classes, plus any existing overlaps."""
    student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    enrollments = (await db.execute(
        select(Enrollment).where(Enrollment.student_id == student_id)
        .order_by(Enrollment.created_at.asc()))).scalars().all()
    fee_plan = next((e.fee_plan for e in enrollments if e.fee_plan), None)
    expected = _expected_classes(fee_plan)

    year, mon = (int(x) for x in month.split("-"))
    first = date(year, mon, 1)
    import calendar as _cal
    last = date(year, mon, _cal.monthrange(year, mon)[1])

    sessions = (await db.execute(
        select(ClassSession).where(ClassSession.student_id == student_id,
                                   ClassSession.scheduled_date >= first,
                                   ClassSession.scheduled_date <= last)
        .order_by(ClassSession.scheduled_date, ClassSession.scheduled_start))).scalars().all()

    def sess_out(s):
        return {"id": str(s.id), "date": s.scheduled_date.isoformat(),
                "start": s.scheduled_start.strftime("%H:%M"), "end": s.scheduled_end.strftime("%H:%M"),
                "status": s.status, "enrollment_id": str(s.enrollment_id),
                "instructor_id": str(s.instructor_id) if s.instructor_id else None,
                "counts": bool(s.counts_toward_package)}

    active = [s for s in sessions if s.status != "cancelled"]
    counts = {
        "scheduled": sum(1 for s in active if s.status in ("scheduled", "rescheduled")),
        "completed": sum(1 for s in active if s.status == "completed"),
        "needs_reschedule": sum(1 for s in active if s.status == "rescheduling_required"),
        "cancelled": sum(1 for s in sessions if s.status == "cancelled"),
    }
    remaining = max((expected or 0) - len(active), 0) if expected else None

    # existing overlaps inside this month (data hygiene — reported, never auto-fixed)
    existing_conflicts = []
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            if a.scheduled_date == b.scheduled_date and _slot_overlaps(
                    a.scheduled_start, a.scheduled_end, b.scheduled_start, b.scheduled_end):
                existing_conflicts.append({
                    "type": "existing_overlap",
                    "date": a.scheduled_date.isoformat(),
                    "message": f"Existing classes overlap on {a.scheduled_date.day} {_MONTH_NAMES[a.scheduled_date.month]}, "
                               f"{_fmt12(a.scheduled_start)}-{_fmt12(a.scheduled_end)} and "
                               f"{_fmt12(b.scheduled_start)}-{_fmt12(b.scheduled_end)}.",
                })
    return {
        "month": month,
        "plan": {"fee_plan": fee_plan, "classes_expected": expected,
                 "label": {4: "4 classes / month", 8: "8 classes / month"}.get(expected, None)},
        "enrollments": [{"id": str(e.id), "programme_name": e.programme_name, "fee_plan": e.fee_plan,
                         "status": e.status,
                         "instructor_id": str(e.instructor_id) if e.instructor_id else None} for e in enrollments],
        "sessions": [sess_out(s) for s in sessions],
        "counts": counts,
        "scheduled_total": len(active),
        "remaining": remaining,
        "existing_conflicts": existing_conflicts,
    }


@router.post("/students/{student_id}/monthly-schedule")
async def admin_save_monthly_schedule(
    student_id: UUID,
    body: MonthlyScheduleSave,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Save a month's class slots after conflict checking.

    Conflicts (instructor busy, student busy, overlapping interval, weekly
    timetable clashes) block the whole request with specific messages —
    nothing is silently moved or replaced.  Exact duplicates of already
    existing sessions are skipped so re-saving is idempotent.  Completed
    sessions are never modified.
    """
    student = (await db.execute(select(Student).where(Student.id == student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    enrollment = await _resolve_student_enrollment(db, student, body.enrollment_id)

    try:
        year, mon = (int(x) for x in body.month.split("-"))
        first = date(year, mon, 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    import calendar as _cal
    last = date(year, mon, _cal.monthrange(year, mon)[1])
    if not (1 <= mon <= 12):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")

    if not body.classes:
        raise HTTPException(status_code=400, detail="No class slots provided")

    default_instructor = body.instructor_id or enrollment.instructor_id
    if not default_instructor:
        raise HTTPException(status_code=400,
                            detail="Assign an instructor to the enrolment before scheduling classes")

    # parse + validate rows
    parsed: list[tuple[date, dtime, dtime, Optional[UUID]]] = []
    seen_slots = set()
    for c in body.classes:
        try:
            d = date.fromisoformat(c.date)
            s_t = dtime.fromisoformat(c.start_time)
            e_t = dtime.fromisoformat(c.end_time)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"Invalid class slot: {c.date} {c.start_time}-{c.end_time} "
                                       "(use YYYY-MM-DD and HH:MM)")
        if not (first <= d <= last):
            raise HTTPException(status_code=400,
                                detail=f"{d.isoformat()} is outside the selected month {body.month}")
        if s_t >= e_t:
            raise HTTPException(status_code=400,
                                detail=f"End time must be after start time on {d.isoformat()}")
        inst = c.instructor_id or default_instructor
        key = (d.isoformat(), s_t.isoformat())
        if key in seen_slots:
            raise HTTPException(status_code=400,
                                detail=f"Duplicate slot in request: {d.isoformat()} {_fmt12(s_t)}")
        seen_slots.add(key)
        parsed.append((d, s_t, e_t, inst))

    # ---- conflict detection (whole request blocked if any conflict) ----
    conflicts: list[dict] = []
    to_insert: list[tuple] = []
    skipped_duplicates = 0

    # existing sessions for this student + for each instructor involved
    student_sessions = (await db.execute(
        select(ClassSession).where(ClassSession.student_id == student_id,
                                   ClassSession.scheduled_date >= first,
                                   ClassSession.scheduled_date <= last,
                                   ClassSession.status != "cancelled"))).scalars().all()
    inst_ids = {p[3] for p in parsed if p[3]}
    instr_sessions = (await db.execute(
        select(ClassSession).where(ClassSession.instructor_id.in_(list(inst_ids)),
                                   ClassSession.scheduled_date >= first,
                                   ClassSession.scheduled_date <= last,
                                   ClassSession.status != "cancelled"))).scalars().all() if inst_ids else []
    # weekly timetables: this student's + the involved instructors'
    student_enr_ids = [e.id for e in (await db.execute(
        select(Enrollment).where(Enrollment.student_id == student_id))).scalars().all()]
    student_weekly = (await db.execute(
        select(ClassSchedule).where(ClassSchedule.enrollment_id.in_(student_enr_ids),
                                    ClassSchedule.is_active.is_(True)))).scalars().all() if student_enr_ids else []
    instr_weekly = (await db.execute(
        select(ClassSchedule).where(ClassSchedule.instructor_id.in_(list(inst_ids)),
                                    ClassSchedule.is_active.is_(True)))).scalars().all() if inst_ids else []

    _DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    for d, s_t, e_t, inst in parsed:
        # exact duplicate of an already existing session → skip (idempotent save)
        dup = any(sd.scheduled_date == d and sd.scheduled_start == s_t
                  for sd in student_sessions)
        if dup:
            skipped_duplicates += 1
            continue
        before = len(conflicts)

        # student busy?
        for ss in student_sessions:
            if ss.scheduled_date == d and _slot_overlaps(s_t, e_t, ss.scheduled_start, ss.scheduled_end):
                conflicts.append({
                    "type": "student", "date": d.isoformat(),
                    "message": f"{student.full_name} already has a class scheduled on {d.day} "
                               f"{_MONTH_NAMES[d.month]}, {_fmt12(s_t)}-{_fmt12(e_t)}.",
                })
                break
        # instructor busy (any student)?
        for isess in instr_sessions:
            if isess.student_id != student_id and isess.scheduled_date == d \
                    and _slot_overlaps(s_t, e_t, isess.scheduled_start, isess.scheduled_end):
                conflicts.append({
                    "type": "instructor", "date": d.isoformat(),
                    "message": f"This instructor already has a class scheduled on {d.day} "
                               f"{_MONTH_NAMES[d.month]}, {_fmt12(s_t)}-{_fmt12(e_t)}.",
                })
                break
        # weekly timetable clashes (overlap with recurring rows)
        day_name = _DAY_ORDER[d.weekday()]
        for w in instr_weekly:
            if w.day_of_week == day_name and _slot_overlaps(s_t, e_t, w.start_time, w.end_time):
                conflicts.append({
                    "type": "instructor_weekly", "date": d.isoformat(),
                    "message": f"This instructor already has a weekly class on {day_name.capitalize()}s, "
                               f"{_fmt12(s_t)}-{_fmt12(e_t)} (recurring timetable).",
                })
                break
        for w in student_weekly:
            if w.day_of_week == day_name and _slot_overlaps(s_t, e_t, w.start_time, w.end_time):
                conflicts.append({
                    "type": "student_weekly", "date": d.isoformat(),
                    "message": f"{student.full_name} already has a weekly class on {day_name.capitalize()}s, "
                               f"{_fmt12(s_t)}-{_fmt12(e_t)} (recurring timetable).",
                })
                break

        if len(conflicts) == before:
            to_insert.append((d, s_t, e_t, inst))

    if conflicts:
        raise HTTPException(status_code=409, detail={
            "message": "Scheduling conflicts must be resolved before saving.",
            "conflicts": conflicts,
        })

    # ---- insert (children of this student only; completed sessions untouched) ----
    created_rows = []
    for d, s_t, e_t, inst in to_insert:
        row = ClassSession(
            id=uuid.uuid4(), enrollment_id=enrollment.id, student_id=student_id,
            instructor_id=inst, scheduled_date=d, scheduled_start=s_t, scheduled_end=e_t,
            status=SessionStatus.SCHEDULED, billing_month=body.month,
            counts_toward_package=True, created_by=current_user.id,
        )
        db.add(row)
        created_rows.append(row)
    await db.flush()

    # recompute monthly totals after save
    active_after = (await db.execute(
        select(func.count(ClassSession.id)).where(
            ClassSession.student_id == student_id,
            ClassSession.scheduled_date >= first, ClassSession.scheduled_date <= last,
            ClassSession.status != "cancelled"))).scalar() or 0
    expected = _expected_classes(enrollment.fee_plan)
    remaining = max((expected or 0) - active_after, 0) if expected else None

    await record_audit(
        db, action="student.schedule_saved", entity_type="student", entity_id=str(student_id),
        actor_user_id=current_user.id, actor_role=current_user.role.value,
        summary=f"Scheduled {len(created_rows)} class(es) for {body.month} "
                f"({enrollment.fee_plan or 'plan unset'}; month total {active_after}"
                f"{f'/{expected}' if expected else ''})",
    )
    return {
        "scheduled": [{"date": r.scheduled_date.isoformat(),
                       "start": r.scheduled_start.strftime("%H:%M"),
                       "end": r.scheduled_end.strftime("%H:%M"),
                       "id": str(r.id)} for r in created_rows],
        "skipped_duplicates": skipped_duplicates,
        "month_total": active_after,
        "classes_expected": expected,
        "remaining": remaining,
    }


# ========================================
# Instructor account management (admin CRUD)
# ========================================
class AdminInstructorCreate(BaseModel):
    username: str
    first_name: str
    last_name: str = ""
    phone: Optional[str] = None
    specializations: Optional[str] = None
    qualifications: Optional[str] = None
    experience_years: Optional[str] = None
    bio: Optional[str] = None
    email: Optional[str] = None


class AdminInstructorUpdate(BaseModel):
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    specializations: Optional[str] = None
    qualifications: Optional[str] = None
    experience_years: Optional[str] = None
    bio: Optional[str] = None
    is_active: Optional[bool] = None
    acknowledge_future_classes: Optional[bool] = False


async def _instructor_impact(db: AsyncSession, instructor_id: UUID) -> dict:
    """Affected students + future classes for deactivation confirmation."""
    enrollments = (await db.execute(
        select(Enrollment).where(Enrollment.instructor_id == instructor_id)
    )).scalars().all()
    students = []
    for e in enrollments:
        stu = (await db.execute(select(Student).where(Student.id == e.student_id))).scalar_one_or_none()
        if stu:
            students.append({"name": stu.full_name, "cma_registration_id": stu.cma_registration_id,
                             "programme": e.programme_name})
    sched_count = (await db.execute(
        select(func.count(ClassSchedule.id)).where(
            ClassSchedule.instructor_id == instructor_id,
            ClassSchedule.is_active.is_(True),
        ))).scalar_one()
    future = (await db.execute(
        select(ClassSession).where(
            ClassSession.instructor_id == instructor_id,
            ClassSession.scheduled_date >= date.today(),
            ClassSession.status.in_([SessionStatus.SCHEDULED, SessionStatus.RESCHEDULING_REQUIRED]),
        ).order_by(ClassSession.scheduled_date.asc())
    )).scalars().all()
    return {
        "assigned_students": students,
        "assigned_student_count": len(students),
        "recurring_schedule_rows": sched_count,
        "future_classes": [
            {"date": f.scheduled_date.isoformat(), "start": f.scheduled_start.strftime("%H:%M"),
             "end": f.scheduled_end.strftime("%H:%M")} for f in future
        ],
        "future_class_count": len(future),
    }


@router.post("/instructors", status_code=status.HTTP_201_CREATED)
async def admin_create_instructor(
    body: AdminInstructorCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    username = body.username.strip()
    if not _USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="Login ID must be 3-100 chars (letters, digits, . _ -)")
    if not body.first_name.strip():
        raise HTTPException(status_code=400, detail="First name is required")
    if await _unique_username_exists(db, username):
        raise HTTPException(status_code=409, detail="That login ID is already in use")

    temp_pin = _gen_temp_pin()
    user = User(
        email=body.email.lower() if body.email else None,
        username=username,
        hashed_password=get_password_hash(temp_pin),
        role=UserRole.INSTRUCTOR,
        is_active=True,
        must_change_pin=True,
    )
    db.add(user)
    await db.flush()

    instructor = Instructor(
        user_id=user.id,
        first_name=body.first_name.strip(),
        last_name=(body.last_name or "").strip(),
        phone=(body.phone or "").strip() or None,
        specializations=(body.specializations or "").strip() or None,
        qualifications=(body.qualifications or "").strip() or None,
        experience_years=(body.experience_years or "").strip() or None,
        bio=(body.bio or "").strip() or None,
        is_active=True,
    )
    db.add(instructor)
    await db.flush()
    await record_audit(
        db,
        action="instructor.created",
        entity_type="instructor",
        entity_id=str(instructor.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Created instructor {instructor.first_name} {instructor.last_name} (login {username})",
    )
    await db.flush()
    return {
        "id": str(instructor.id),
        "login_id": username,
        "name": f"{instructor.first_name} {instructor.last_name}",
        "temp_pin": temp_pin,            # shown to admin exactly once
        "must_change_pin": True,
    }


@router.get("/instructors/{instructor_id}/impact")
async def instructor_deactivation_impact(
    instructor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    instructor = (await db.execute(select(Instructor).where(Instructor.id == instructor_id))).scalar_one_or_none()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")
    return await _instructor_impact(db, instructor_id)


@router.patch("/instructors/{instructor_id}")
async def admin_update_instructor(
    instructor_id: UUID,
    body: AdminInstructorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    instructor = (await db.execute(select(Instructor).where(Instructor.id == instructor_id))).scalar_one_or_none()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")
    user = (await db.execute(select(User).where(User.id == instructor.user_id))).scalar_one_or_none()

    # Deactivation requires resolving (or explicitly acknowledging) future classes
    if body.is_active is False and (not instructor.is_active or (user and not user.is_active)):
        pass
    if body.is_active is False:
        impact = await _instructor_impact(db, instructor_id)
        if impact["future_class_count"] > 0 and not body.acknowledge_future_classes:
            raise HTTPException(
                status_code=409,
                detail="Future classes are still assigned to this instructor — reassign them or explicitly acknowledge",
            )

    before = {"is_active": bool(instructor.is_active), "specializations": instructor.specializations}
    if body.username is not None and user:
        new_username = body.username.strip()
        if not _USERNAME_RE.match(new_username):
            raise HTTPException(status_code=400, detail="Login ID must be 3-100 chars (letters, digits, . _ -)")
        if new_username != user.username and await _unique_username_exists(db, new_username, exclude_user_id=user.id):
            raise HTTPException(status_code=409, detail="That login ID is already in use")
        user.username = new_username
        db.add(user)
    if body.first_name is not None and body.first_name.strip():
        instructor.first_name = body.first_name.strip()
    if body.last_name is not None:
        instructor.last_name = body.last_name.strip()
    for field in ("phone", "specializations", "qualifications", "experience_years", "bio"):
        value = getattr(body, field)
        if value is not None:
            setattr(instructor, field, value.strip() or None)
    if body.is_active is not None:
        instructor.is_active = body.is_active
        if user:
            user.is_active = body.is_active
            db.add(user)
    db.add(instructor)
    await db.flush()
    await record_audit(
        db,
        action="instructor.updated" if body.is_active is not False else "instructor.deactivated",
        entity_type="instructor",
        entity_id=str(instructor.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        before_data=before,
        after_data={"is_active": bool(instructor.is_active), "specializations": instructor.specializations},
        summary=f"{instructor.first_name} {instructor.last_name}: "
                + ("deactivated" if body.is_active is False else "updated"),
    )
    result = await db.execute(select(Instructor).where(Instructor.id == instructor.id))
    i = result.scalar_one()
    return {"id": str(i.id), "is_active": bool(i.is_active),
            "name": f"{i.first_name} {i.last_name}", "specializations": i.specializations}


@router.delete("/instructors/{instructor_id}")
async def admin_delete_instructor(
    instructor_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Remove an instructor only when NO history exists; otherwise deactivate."""
    instructor = (await db.execute(
        select(Instructor).where(Instructor.id == instructor_id))).scalar_one_or_none()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")

    history = {}
    history["enrollments"] = (await db.execute(
        select(func.count(Enrollment.id)).where(Enrollment.instructor_id == instructor.id))).scalar_one()
    history["sessions"] = (await db.execute(
        select(func.count(ClassSession.id)).where(ClassSession.instructor_id == instructor.id))).scalar_one()
    history["schedules"] = (await db.execute(
        select(func.count(ClassSchedule.id)).where(ClassSchedule.instructor_id == instructor.id))).scalar_one()
    if any(history.values()):
        raise HTTPException(
            status_code=409,
            detail="This instructor has teaching history — deactivate instead of deleting "
                   "(PATCH is_active=false); all history is preserved",
        )

    user_id = instructor.user_id
    await db.delete(instructor)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user:
        await db.delete(user)
    await db.flush()
    await record_audit(
        db,
        action="instructor.deleted",
        entity_type="instructor",
        entity_id=str(instructor_id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Deleted instructor {instructor.first_name} {instructor.last_name} (no historical records)",
    )
    return {"deleted": True, "id": str(instructor_id)}


# ========================================
# Assign instructor to enrollment + recurring timetable
# ========================================
class AssignInstructorIn(BaseModel):
    instructor_id: Optional[UUID] = None    # None = unassign
    confirm_conflicts: bool = False


def _times_overlap(a_start: dtime, a_end: dtime, b_start: dtime, b_end: dtime) -> bool:
    return a_start < b_end and b_start < a_end


def _hhmm(value: str) -> dtime:
    h, m = value.split(":")
    return dtime(int(h), int(m))


@router.get("/instructors/{instructor_id}/availability")
async def instructor_availability(
    instructor_id: UUID,
    day: str,
    start: str,
    end: str,
    exclude_enrollment_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    instructor = (await db.execute(select(Instructor).where(Instructor.id == instructor_id))).scalar_one_or_none()
    if not instructor:
        raise HTTPException(status_code=404, detail="Instructor not found")
    conflicts = await _collect_instructor_conflicts(
        db, instructor_id, day.strip().lower(), _hhmm(start), _hhmm(end), exclude_enrollment_id
    )
    user = (await db.execute(select(User).where(User.id == instructor.user_id))).scalar_one_or_none()
    return {
        "instructor": {
            "id": str(instructor.id),
            "name": f"{instructor.first_name} {instructor.last_name}",
            "specializations": instructor.specializations,
            "is_active": bool(instructor.is_active),
            "login_id": user.username if user else None,
        },
        "conflicts": conflicts,
        "available": len(conflicts) == 0,
    }


async def _collect_instructor_conflicts(
    db: AsyncSession,
    instructor_id: UUID,
    day: str,
    start: dtime,
    end: dtime,
    exclude_enrollment_id: UUID = None,
) -> list:
    conflicts = []
    # recurring timetable clashes (other students)
    q = (select(ClassSchedule, Enrollment, Student)
         .join(Enrollment, Enrollment.id == ClassSchedule.enrollment_id)
         .join(Student, Student.id == Enrollment.student_id)
         .where(ClassSchedule.instructor_id == instructor_id,
                ClassSchedule.is_active.is_(True),
                ClassSchedule.day_of_week == day))
    if exclude_enrollment_id:
        q = q.where(ClassSchedule.enrollment_id != exclude_enrollment_id)
    for sched, enr, stu in (await db.execute(q)).all():
        if _times_overlap(start, end, sched.start_time, sched.end_time):
            conflicts.append({
                "kind": "recurring",
                "day": sched.day_of_week,
                "start": sched.start_time.strftime("%H:%M"),
                "end": sched.end_time.strftime("%H:%M"),
                "student": stu.full_name,
                "cma_registration_id": stu.cma_registration_id,
                "programme": enr.programme_name,
            })
    # dated session clashes
    day_idx = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
               "friday": 4, "saturday": 5, "sunday": 6}.get(day, -1)
    if day_idx >= 0:
        q = (select(ClassSession, Enrollment, Student)
             .join(Enrollment, Enrollment.id == ClassSession.enrollment_id)
             .join(Student, Student.id == Enrollment.student_id)
             .where(ClassSession.instructor_id == instructor_id,
                    ClassSession.status.in_([SessionStatus.SCHEDULED, SessionStatus.RESCHEDULING_REQUIRED])))
        if exclude_enrollment_id:
            q = q.where(ClassSession.enrollment_id != exclude_enrollment_id)
        for sess, enr, stu in (await db.execute(q)).all():
            if sess.scheduled_date.weekday() == day_idx and _times_overlap(start, end, sess.scheduled_start, sess.scheduled_end):
                conflicts.append({
                    "kind": "session",
                    "date": sess.scheduled_date.isoformat(),
                    "start": sess.scheduled_start.strftime("%H:%M"),
                    "end": sess.scheduled_end.strftime("%H:%M"),
                    "student": stu.full_name,
                    "cma_registration_id": stu.cma_registration_id,
                })
    return conflicts


class AdminEnrollmentUpdate(BaseModel):
    programme_name: Optional[str] = None
    programme_id: Optional[str] = None
    fee_plan: Optional[str] = None          # 4_classes | 8_classes | '' (unassigned)
    fee_amount: Optional[float] = None
    status: Optional[str] = None            # active | completed | cancelled


@router.patch("/enrollments/{enrollment_id}")
async def admin_update_enrollment(
    enrollment_id: UUID,
    body: AdminEnrollmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Edit an enrolment's programme/fee plan — never silently rewrites history."""
    enrollment = (await db.execute(select(Enrollment).where(Enrollment.id == enrollment_id))).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    before = {"programme_name": enrollment.programme_name, "fee_plan": enrollment.fee_plan,
              "fee_amount": float(enrollment.fee_amount) if enrollment.fee_amount else None,
              "status": enrollment.status}

    if body.programme_id is not None and body.programme_id.strip():
        enrollment.programme_id = body.programme_id.strip()
    if body.programme_name is not None and body.programme_name.strip():
        enrollment.programme_name = body.programme_name.strip()
    if body.fee_plan is not None:
        plan = body.fee_plan.strip()
        if plan and plan not in _ALLOWED_FEE_PLANS:
            raise HTTPException(status_code=400, detail="fee_plan must be 4_classes, 8_classes or empty")
        enrollment.fee_plan = plan or None
    if body.fee_amount is not None:
        if body.fee_amount < 0:
            raise HTTPException(status_code=400, detail="fee_amount cannot be negative")
        enrollment.fee_amount = body.fee_amount
    if body.status is not None:
        if body.status not in {"active", "completed", "cancelled"}:
            raise HTTPException(status_code=400, detail="status must be active, completed or cancelled")
        enrollment.status = body.status

    db.add(enrollment)
    await db.flush()
    await record_audit(
        db,
        action="enrollment.updated",
        entity_type="enrollment",
        entity_id=str(enrollment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        before_data=before,
        after_data={"programme_name": enrollment.programme_name, "fee_plan": enrollment.fee_plan,
                    "fee_amount": float(enrollment.fee_amount) if enrollment.fee_amount else None,
                    "status": enrollment.status},
    )
    return {"id": str(enrollment.id), "programme_name": enrollment.programme_name,
            "fee_plan": enrollment.fee_plan,
            "fee_amount": float(enrollment.fee_amount) if enrollment.fee_amount else None,
            "status": enrollment.status}


@router.post("/enrollments/{enrollment_id}/instructor")
async def assign_enrollment_instructor(
    enrollment_id: UUID,
    body: AssignInstructorIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Assign/reassign/unassign an instructor on an enrolment AND its
    recurring weekly timetable rows. Conflicts are reported and must be
    explicitly confirmed — nothing is ever silently overwritten."""
    enrollment = (await db.execute(select(Enrollment).where(Enrollment.id == enrollment_id))).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    instructor = None
    if body.instructor_id is not None:
        instructor = (await db.execute(select(Instructor).where(Instructor.id == body.instructor_id))).scalar_one_or_none()
        if not instructor:
            raise HTTPException(status_code=404, detail="Instructor not found")
        if not instructor.is_active:
            raise HTTPException(status_code=400, detail="That instructor is deactivated")

    before = {"instructor_id": str(enrollment.instructor_id) if enrollment.instructor_id else None}
    conflicts = []
    if instructor:
        schedule_rows = (await db.execute(
            select(ClassSchedule).where(
                ClassSchedule.enrollment_id == enrollment.id,
                ClassSchedule.is_active.is_(True),
            ))).scalars().all()
        for row in schedule_rows:
            clashes = await _collect_instructor_conflicts(
                db, instructor.id, row.day_of_week, row.start_time, row.end_time, exclude_enrollment_id=enrollment.id
            )
            conflicts.extend(clashes)
        # de-duplicate conflicts
        uniq, seen = [], set()
        for c in conflicts:
            key = (c.get("kind"), c.get("day"), c.get("date"), c.get("start"), c.get("student"))
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        conflicts = uniq

        if conflicts and not body.confirm_conflicts:
            raise HTTPException(status_code=409, detail={
                "message": "This instructor already has classes in the proposed slots — confirm to assign anyway "
                           "(no existing class is moved or deleted)",
                "conflicts": conflicts,
            })

    # persist: enrolment + every active recurring row of this enrolment
    enrollment.instructor_id = instructor.id if instructor else None
    db.add(enrollment)
    schedule_rows = (await db.execute(
        select(ClassSchedule).where(
            ClassSchedule.enrollment_id == enrollment.id,
            ClassSchedule.is_active.is_(True),
        ))).scalars().all()
    updated_rows = 0
    for row in schedule_rows:
        row.instructor_id = instructor.id if instructor else None
        db.add(row)
        updated_rows += 1

    # propagate to concrete class occurrences that have not been delivered yet
    # so every authorised portal sees the same teacher on the same lesson
    sess_result = await db.execute(
        update(ClassSession)
        .where(
            ClassSession.enrollment_id == enrollment.id,
            ClassSession.status.in_(["scheduled", "rescheduling_required"]),
        )
        .values(instructor_id=instructor.id if instructor else None)
    )
    sessions_updated = sess_result.rowcount or 0

    await db.flush()
    await record_audit(
        db,
        action="instructor.assigned" if instructor else "instructor.unassigned",
        entity_type="enrollment",
        entity_id=str(enrollment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        before_data=before,
        after_data={"instructor_id": str(instructor.id) if instructor else None,
                    "schedule_rows_updated": updated_rows,
                    "class_sessions_updated": sessions_updated},
        summary=(f"{'Assigned' if instructor else 'Unassigned'} "
                 f"{(f'{instructor.first_name} {instructor.last_name}' if instructor else 'instructor')} "
                 f"to enrolment ({enrollment.programme_name}, {updated_rows} weekly row(s))"
                 + (f" with {len(conflicts)} confirmed conflict(s)" if conflicts else "")),
    )
    return {
        "enrollment_id": str(enrollment.id),
        "instructor_id": str(instructor.id) if instructor else None,
        "instructor_name": f"{instructor.first_name} {instructor.last_name}" if instructor else None,
        "schedule_rows_updated": updated_rows,
        "confirmed_conflicts": len(conflicts),
    }


# ========================================
# Explicit account provisioning from an approved application
# ========================================
class ProvisionStudentIn(BaseModel):
    """Optional admin-supplied provisioning details.

    Anything left blank is generated/derived — the admin can assign the
    CMA Roll Number (login id), the temporary PIN, the fee plan and the
    instructor in one explicit step."""
    login_id: Optional[str] = None        # CMA Roll Number to use as the sign-in id
    temp_pin: Optional[str] = None        # 4-digit temporary PIN (issued once)
    fee_plan: Optional[str] = None        # 4_classes | 8_classes
    fee_amount: Optional[float] = None    # rupees (consistent with enrollment.fee_amount)
    instructor_id: Optional[UUID] = None


@router.post("/registration-requests/{request_id}/provision", status_code=status.HTTP_201_CREATED)
async def provision_student_from_application(
    request_id: UUID,
    body: Optional[ProvisionStudentIn] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Second, explicit step: create the student account from an approved
    application (never happens automatically on approval).

    Issues a temporary PIN (returned once, stored as a hash only) and forces
    a PIN change on first login.
    """
    req = (await db.execute(select(RegistrationRequest).where(RegistrationRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Registration request not found")
    if req.status != RegistrationRequestStatus.APPROVED:
        raise HTTPException(status_code=400, detail="Approve the application before provisioning an account")
    if req.student_id:
        existing = (await db.execute(select(Student).where(Student.id == req.student_id))).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="An account already exists for this application")

    name_parts = req.full_name.strip().split(" ", 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    body = body or ProvisionStudentIn()
    cma_id = await CMAIdService.generate_cma_id(db)
    if body.login_id:
        login_id = body.login_id.strip()
        if not login_id:
            raise HTTPException(status_code=400, detail="login_id must not be empty")
        clash = (await db.execute(select(User).where(User.username == login_id))).scalar_one_or_none()
        if clash:
            raise HTTPException(status_code=409, detail="That login id is already in use")
    else:
        login_id = cma_id
    if body.temp_pin:
        if not re.fullmatch(r"\d{4}", body.temp_pin):
            raise HTTPException(status_code=400, detail="temp_pin must be exactly 4 digits")
        temp_pin = body.temp_pin
    else:
        temp_pin = _gen_temp_pin()
    if body.fee_plan is not None and body.fee_plan not in _ALLOWED_FEE_PLANS:
        raise HTTPException(status_code=400, detail="fee_plan must be 4_classes or 8_classes")

    user = User(
        email=req.email.lower() if req.email else None,
        username=login_id,                  # login id = admin-chosen or generated CMA Roll Number
        hashed_password=get_password_hash(temp_pin),
        role=UserRole.STUDENT,
        is_active=True,
        must_change_pin=True,
    )
    db.add(user)
    await db.flush()

    slug = re.sub(r"[^a-z0-9]+", "-", first_name.lower()).strip("-") or "student"
    base, n = slug, 1
    while (await db.execute(select(Student).where(Student.portal_slug == slug))).scalar_one_or_none():
        n += 1
        slug = f"{base}-{n}"

    student = Student(
        user_id=user.id,
        cma_registration_id=cma_id,
        portal_slug=slug,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=req.date_of_birth,
        address=req.address,
        phone=req.mobile,
        status="active",
        profile_complete=bool(req.date_of_birth),
        notes=f"Provisioned from application {req.request_id}",
    )
    db.add(student)
    await db.flush()

    if req.guardian_name:
        g_parts = req.guardian_name.strip().split(" ", 1)
        db.add(Guardian(
            student_id=student.id,
            first_name=g_parts[0],
            last_name=g_parts[1] if len(g_parts) > 1 else "",
            guardian_relationship=(req.guardian_relationship or "parent").lower(),
            phone=req.guardian_mobile or req.mobile,
            email=req.guardian_email,
            is_primary="Y",
        ))
        await db.flush()

    enrollments = []
    for programme in (req.selected_programmes or []):
        pid = programme.get("id") if isinstance(programme, dict) else str(programme)
        pname = programme.get("name") if isinstance(programme, dict) else str(programme)
        instructor = None
        if body.instructor_id:
            instructor = (await db.execute(
                select(Instructor).where(Instructor.id == body.instructor_id))).scalar_one_or_none()
            if not instructor or not instructor.is_active:
                raise HTTPException(status_code=400, detail="instructor_id is not an active instructor")
        enrollment = Enrollment(
            student_id=student.id,
            programme_id=pid,
            programme_name=pname,
            instructor_id=instructor.id if instructor else None,
            fee_plan=body.fee_plan,
            # fee_amount is stored in RUPEES across the codebase (enrollment model)
            fee_amount=body.fee_amount if body.fee_amount is not None else (
                4500.0 if body.fee_plan == "4_classes" else 8000.0 if body.fee_plan == "8_classes" else None),
            status=EnrollmentStatus.ACTIVE,
            start_date=date.today(),
        )
        db.add(enrollment)
        enrollments.append(pname)
    await db.flush()

    req.student_id = student.id
    db.add(req)
    await db.flush()

    await record_audit(
        db,
        action="registration.provisioned",
        entity_type="registration_request",
        entity_id=req.request_id,
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"Provisioned account {cma_id} for {student.full_name} from {req.request_id} (temp PIN issued)",
    )
    await notify_user(
        db,
        user_id=user.id,
        type="welcome",
        title="Welcome to ChankArts Academy",
        body=f"Your Roll No. is {login_id}. You must choose a new PIN at your first sign-in.",
        dedupe_key=f"provision:{req.request_id}",
    )
    await db.flush()

    return {
        "message": "Student account created",
        "request_id": req.request_id,
        "student_id": str(student.id),
        "login_id": login_id,
        "cma_registration_id": cma_id,
        "fee_plan": body.fee_plan,
        "instructor_id": str(body.instructor_id) if body.instructor_id else None,
        "full_name": student.full_name,
        "enrolments": enrollments,
        "temp_pin": temp_pin,          # shown to the admin exactly once
        "must_change_pin": True,
    }


# ========================================
# Instructor / class-completion reports
# ========================================
@router.get("/reports/class-completion")
async def class_completion_report(
    instructor_id: Optional[UUID] = None,
    student_id: Optional[UUID] = None,
    programme: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Completion report built from real class-session records.

    Past classes still marked `scheduled` are reported as awaiting update —
    they are never auto-completed. Future classes are shown separately.
    """
    q = (
        select(ClassSession, Enrollment, Student, Instructor, User)
        .join(Enrollment, Enrollment.id == ClassSession.enrollment_id)
        .join(Student, Student.id == ClassSession.student_id)
        .outerjoin(Instructor, Instructor.id == ClassSession.instructor_id)
        .outerjoin(User, User.id == Instructor.user_id)
    )
    conds = []
    if instructor_id:
        conds.append(ClassSession.instructor_id == instructor_id)
    if student_id:
        conds.append(ClassSession.student_id == student_id)
    if programme:
        conds.append(Enrollment.programme_name.ilike(f"%{programme}%"))
    if date_from:
        conds.append(ClassSession.scheduled_date >= date.fromisoformat(date_from))
    if date_to:
        conds.append(ClassSession.scheduled_date <= date.fromisoformat(date_to))
    if status_filter:
        conds.append(ClassSession.status == status_filter)
    if conds:
        q = q.where(and_(*conds))
    q = q.order_by(ClassSession.scheduled_date.asc(), ClassSession.scheduled_start.asc())

    rows = (await db.execute(q)).all()
    today = date.today()

    sessions = []
    per_instructor = {}
    counts = {"completed": 0, "scheduled_upcoming": 0, "awaiting_update": 0,
              "cancelled": 0, "rescheduled": 0, "reschedule_requested": 0}
    last_completion = None

    for sess, enr, stu, instr, iuser in rows:
        status = sess.status
        if status == SessionStatus.COMPLETED:
            bucket = "completed"
        elif status == SessionStatus.CANCELLED:
            bucket = "cancelled"
        elif status == SessionStatus.RESCHEDULED:
            bucket = "rescheduled"
        elif status == SessionStatus.RESCHEDULING_REQUIRED:
            bucket = "reschedule_requested"
        elif sess.scheduled_date < today:
            bucket = "awaiting_update"
        else:
            bucket = "scheduled_upcoming"
        counts[bucket] += 1

        updated = sess.updated_at.isoformat() if (bucket == "completed" and sess.updated_at) else None
        if bucket == "completed":
            ts = sess.actual_date.isoformat() if sess.actual_date else None
            if ts and (last_completion is None or ts > last_completion):
                last_completion = ts

        key = str(sess.instructor_id) if sess.instructor_id else "unassigned"
        if key not in per_instructor:
            per_instructor[key] = {
                "instructor_id": str(sess.instructor_id) if sess.instructor_id else None,
                "instructor_name": f"{instr.first_name} {instr.last_name}" if instr else "Unassigned",
                "login_id": iuser.username if iuser else None,
                "completed": 0, "scheduled_upcoming": 0, "awaiting_update": 0,
                "cancelled": 0, "rescheduled": 0, "reschedule_requested": 0,
                "last_completion": None,
                "lesson_notes": [],
            }
        per_instructor[key][bucket] += 1
        if updated and (per_instructor[key]["last_completion"] is None or updated > per_instructor[key]["last_completion"]):
            per_instructor[key]["last_completion"] = updated
        if sess.faculty_remarks and bucket == "completed":
            per_instructor[key]["lesson_notes"].append({
                "date": sess.scheduled_date.isoformat(),
                "student": stu.full_name,
                "notes": sess.faculty_remarks,
            })

        sessions.append({
            "id": str(sess.id),
            "scheduled_date": sess.scheduled_date.isoformat(),
            "scheduled_start": sess.scheduled_start.strftime("%H:%M"),
            "scheduled_end": sess.scheduled_end.strftime("%H:%M"),
            "status": status,
            "bucket": bucket,
            "student_name": stu.full_name,
            "student_cma": stu.cma_registration_id,
            "programme": enr.programme_name,
            "instructor_name": f"{instr.first_name} {instr.last_name}" if instr else None,
            "topics_covered": sess.topics_covered,
            "faculty_remarks": sess.faculty_remarks,
            "practice_recommendations": sess.practice_recommendations,
            "actual_date": sess.actual_date.isoformat() if sess.actual_date else None,
            "updated_at": sess.updated_at.isoformat() if sess.updated_at else None,
        })

    past_deliverable = counts["completed"] + counts["awaiting_update"]
    completion_rate = round(100.0 * counts["completed"] / past_deliverable, 1) if past_deliverable else None

    return {
        "filters": {
            "instructor_id": str(instructor_id) if instructor_id else None,
            "student_id": str(student_id) if student_id else None,
            "programme": programme,
            "date_from": date_from,
            "date_to": date_to,
            "status": status_filter,
        },
        "totals": {
            **counts,
            "total": len(sessions),
            "completion_rate_pct": completion_rate,
            "last_completion_update": last_completion,
        },
        "by_instructor": sorted(per_instructor.values(), key=lambda x: x["instructor_name"] or ""),
        "sessions": sessions,
    }
