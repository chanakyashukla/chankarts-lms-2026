"""
Class session scheduling, completion and rescheduling.

Status model (no absence concept anywhere):
  scheduled              -> amber
  completed              -> green
  rescheduling_required  -> red (time must be moved — never "absent")
  cancelled              -> neutral
"""
from datetime import date, datetime, time, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.roles import Permission, UserRole, has_permission
from app.database import get_db
from app.models.class_schedule import ClassSchedule
from app.models.enrollment import Enrollment
from app.models.instructor import Instructor
from app.models.session import ClassSession, SessionStatus, SessionStatusHistory
from app.models.student import Student
from app.models.user import User
from app.services.access import (
    can_access_student,
    get_instructor_for_user,
    get_linked_student_ids,
    require_student_access,
)
from app.services.audit import record_audit
from app.services.notifications import notify_user

router = APIRouter()

MIN_STANDARD_DURATION = 60
MIN_EXCEPTION_DURATION = 30

# --- 24-hour rescheduling notice policy ---------------------------------
# The same wording is shown in the student portal, instructor schedule and
# admin screens — keep them identical.
RESCHEDULE_NOTICE_HOURS = 24
RESCHEDULE_POLICY_TEXT = (
    "Rescheduling requests must be made at least 24 hours before the class "
    "start time. Inside 24 hours, please contact the academy directly."
)
ACADEMY_TZ_NAME = "Asia/Kolkata"


def _session_start_dt(session) -> datetime:
    """Class start as a timezone-aware datetime in the academy timezone."""
    from zoneinfo import ZoneInfo
    tz_name = session.timezone or ACADEMY_TZ_NAME
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(ACADEMY_TZ_NAME)
    return datetime.combine(session.scheduled_date, session.scheduled_start, tzinfo=tz)


def _hours_until_start(session) -> float:
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo(ACADEMY_TZ_NAME))
    return (_session_start_dt(session) - now).total_seconds() / 3600.0


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date. Use YYYY-MM-DD.")


def _parse_time(value: str) -> time:
    try:
        parts = value.split(":")
        return time(int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid time. Use HH:MM (24h).")


def _minutes_between(start: time, end: time) -> int:
    start_min = start.hour * 60 + start.minute
    end_min = end.hour * 60 + end.minute
    if end_min <= start_min:
        end_min += 24 * 60
    return end_min - start_min


class SessionCreate(BaseModel):
    enrollment_id: UUID
    scheduled_date: str
    scheduled_start: str
    scheduled_end: str
    duration_minutes: Optional[int] = None
    is_online: bool = False
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    is_duration_exception: bool = False
    exception_note: Optional[str] = None
    allow_overlap: bool = False


class SessionUpdate(BaseModel):
    scheduled_date: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None
    duration_minutes: Optional[int] = None
    is_online: Optional[bool] = None
    location: Optional[str] = None
    meeting_link: Optional[str] = None
    allow_overlap: bool = False


class CompleteSession(BaseModel):
    actual_date: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    actual_duration_minutes: Optional[int] = None
    topics_covered: Optional[str] = None
    faculty_remarks: Optional[str] = None
    practice_recommendations: Optional[str] = None


class SessionCorrection(BaseModel):
    """Administrator correction of a recorded class (audit-trailed)."""
    actual_date: Optional[str] = None
    actual_start: Optional[str] = None
    actual_end: Optional[str] = None
    actual_duration_minutes: Optional[int] = None
    topics_covered: Optional[str] = None
    faculty_remarks: Optional[str] = None
    practice_recommendations: Optional[str] = None
    reason: str = Field(..., min_length=3)


class RescheduleRequest(BaseModel):
    new_date: str
    new_start: str
    new_end: str
    reason: str = Field(..., min_length=3)
    duration_minutes: Optional[int] = None


class RescheduleExceptionIn(RescheduleRequest):
    """Administrator-only late change: a reason is always mandatory and the
    action is recorded as a policy exception in the audit trail."""
    reason: str = Field(..., min_length=8)


def _serialize(session: ClassSession) -> dict:
    return {
        "id": str(session.id),
        "enrollment_id": str(session.enrollment_id),
        "student_id": str(session.student_id),
        "instructor_id": str(session.instructor_id) if session.instructor_id else None,
        "scheduled_date": session.scheduled_date.isoformat(),
        "scheduled_start": session.scheduled_start.strftime("%H:%M"),
        "scheduled_end": session.scheduled_end.strftime("%H:%M"),
        "timezone": session.timezone,
        "duration_minutes": session.duration_minutes,
        "actual_date": session.actual_date.isoformat() if session.actual_date else None,
        "actual_start": session.actual_start.strftime("%H:%M") if session.actual_start else None,
        "actual_end": session.actual_end.strftime("%H:%M") if session.actual_end else None,
        "actual_duration_minutes": session.actual_duration_minutes,
        "status": session.status,
        "topics_covered": session.topics_covered,
        "faculty_remarks": session.faculty_remarks,
        "reschedule_reason": session.reschedule_reason,
        "replaces_session_id": str(session.replaces_session_id) if session.replaces_session_id else None,
        "is_duration_exception": session.is_duration_exception,
        "exception_note": session.exception_note,
        "practice_recommendations": session.practice_recommendations,
        "counts_toward_package": session.counts_toward_package,
        "billing_month": session.billing_month,
        "is_online": session.is_online,
        "location": session.location,
        "meeting_link": session.meeting_link,
        "preferred_date": session.preferred_date.isoformat() if session.preferred_date else None,
        "preferred_start": session.preferred_start.strftime("%H:%M") if session.preferred_start else None,
        "preferred_end": session.preferred_end.strftime("%H:%M") if session.preferred_end else None,
    }


async def _check_overlap(
    db: AsyncSession,
    *,
    instructor_id: UUID,
    student_id: UUID,
    scheduled_date: date,
    start: time,
    end: time,
    exclude_session_id: Optional[UUID] = None,
) -> Optional[ClassSession]:
    query = select(ClassSession).where(
        ClassSession.scheduled_date == scheduled_date,
        ClassSession.status.in_([SessionStatus.SCHEDULED, SessionStatus.RESCHEDULING_REQUIRED]),
        or_(
            ClassSession.instructor_id == instructor_id,
            ClassSession.student_id == student_id,
        ),
    )
    if exclude_session_id:
        query = query.where(ClassSession.id != exclude_session_id)
    result = await db.execute(query)
    for existing in result.scalars().all():
        if existing.scheduled_start < end and start < existing.scheduled_end:
            return existing
    return None


async def _load_session_for_write(db: AsyncSession, user: User, session_id: UUID) -> ClassSession:
    result = await db.execute(select(ClassSession).where(ClassSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if user.role == UserRole.ADMIN:
        return session
    if user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, user)
        if not instructor or session.instructor_id != instructor.id:
            raise HTTPException(status_code=403, detail="Not your assigned session")
        return session
    if not await can_access_student(db, user, session.student_id):
        raise HTTPException(status_code=403, detail="Access denied")
    # Students/parents may flag a reschedule need, nothing else
    return session


async def _record_history(
    db: AsyncSession,
    session: ClassSession,
    from_status: Optional[str],
    to_status: str,
    user: User,
    reason: Optional[str] = None,
) -> None:
    db.add(
        SessionStatusHistory(
            session_id=session.id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            changed_by=user.id,
        )
    )


@router.get("")
async def list_sessions(
    student_id: Optional[UUID] = None,
    enrollment_id: Optional[UUID] = None,
    instructor_id: Optional[UUID] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(200, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(ClassSession)

    if current_user.role == UserRole.STUDENT:
        linked = await get_linked_student_ids(db, current_user)
        query = query.where(ClassSession.student_id.in_(linked))
    elif current_user.role == UserRole.PARENT:
        linked = await get_linked_student_ids(db, current_user)
        query = query.where(ClassSession.student_id.in_(linked))
    elif current_user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, current_user)
        if not instructor:
            return []
        query = query.where(ClassSession.instructor_id == instructor.id)
    elif not has_permission(current_user.role, Permission.MANAGE_CLASS_SCHEDULE) and not has_permission(
        current_user.role, Permission.VIEW_OWN_SCHEDULE
    ):
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(ClassSession.student_id == student_id)
    if enrollment_id:
        query = query.where(ClassSession.enrollment_id == enrollment_id)
    if instructor_id and current_user.role == UserRole.ADMIN:
        query = query.where(ClassSession.instructor_id == instructor_id)
    if date_from:
        query = query.where(ClassSession.scheduled_date >= _parse_date(date_from))
    if date_to:
        query = query.where(ClassSession.scheduled_date <= _parse_date(date_to))
    if status_filter:
        query = query.where(ClassSession.status == status_filter)

    query = (
        query.order_by(ClassSession.scheduled_date.desc(), ClassSession.scheduled_start.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    sessions = list(result.scalars().all())

    # Enrich every authorized viewer with names they are already scoped to:
    # a student sees their own name, an instructor their assigned students,
    # an admin everyone. Keeps all three portals on one authoritative shape.
    if sessions:
        student_ids = {s.student_id for s in sessions if s.student_id}
        instructor_ids = {s.instructor_id for s in sessions if s.instructor_id}
        enrollment_ids = {s.enrollment_id for s in sessions if s.enrollment_id}
        student_names, instructor_names, programme_names = {}, {}, {}
        student_cmas = {}
        if student_ids:
            rows = await db.execute(
                select(Student.id, Student.first_name, Student.last_name, Student.cma_registration_id)
                .where(Student.id.in_(student_ids))
            )
            student_names = {r.id: f"{r.first_name} {r.last_name}" for r in rows.all()}
            student_cmas = {r.id: r.cma_registration_id for r in rows.all()}
        if instructor_ids:
            rows = await db.execute(
                select(Instructor.id, Instructor.first_name, Instructor.last_name).where(
                    Instructor.id.in_(instructor_ids)
                )
            )
            instructor_names = {r.id: f"{r.first_name} {r.last_name}" for r in rows.all()}
        if enrollment_ids:
            rows = await db.execute(
                select(Enrollment.id, Enrollment.programme_name).where(Enrollment.id.in_(enrollment_ids))
            )
            programme_names = {r.id: r.programme_name for r in rows.all()}
        return [
            dict(
                _serialize(s),
                student_name=student_names.get(s.student_id),
                student_cma=student_cmas.get(s.student_id),
                instructor_name=instructor_names.get(s.instructor_id),
                programme=programme_names.get(s.enrollment_id),
            )
            for s in sessions
        ]

    return [_serialize(s) for s in sessions]


@router.get("/calendar")
async def calendar_view(
    month: str = Query(..., description="YYYY-MM"),
    student_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Month markers for the mini-calendar: one status per day (priority red > green > amber)."""
    try:
        year, mon = int(month.split("-")[0]), int(month.split("-")[1])
        month_start = date(year, mon, 1)
        month_end = date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1) - timedelta(days=1)
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid month. Use YYYY-MM.")

    query = select(ClassSession).where(
        ClassSession.scheduled_date >= month_start,
        ClassSession.scheduled_date <= month_end,
    )

    if current_user.role in (UserRole.STUDENT, UserRole.PARENT):
        linked = await get_linked_student_ids(db, current_user)
        query = query.where(ClassSession.student_id.in_(linked))
    elif current_user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, current_user)
        if not instructor:
            return {"month": month, "days": []}
        query = query.where(ClassSession.instructor_id == instructor.id)

    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(ClassSession.student_id == student_id)

    result = await db.execute(query)
    days: dict[str, dict] = {}
    priority = {
        SessionStatus.RESCHEDULING_REQUIRED: 3,
        SessionStatus.COMPLETED: 2,
        SessionStatus.SCHEDULED: 1,
        SessionStatus.CANCELLED: 0,
    }
    for session in result.scalars().all():
        key = session.scheduled_date.isoformat()
        entry = days.setdefault(key, {"date": key, "statuses": [], "count": 0})
        entry["statuses"].append(session.status)
        entry["count"] += 1
        if priority[session.status] > priority.get(entry.get("marker", SessionStatus.CANCELLED), -1):
            entry["marker"] = session.status

    return {"month": month, "days": sorted(days.values(), key=lambda d: d["date"])}


@router.get("/reschedule-requests")
async def list_reschedule_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Flagged classes awaiting the academy's decision (admin approves/rejects)."""
    rows = (await db.execute(
        select(ClassSession, Enrollment, Student, Instructor)
        .join(Enrollment, Enrollment.id == ClassSession.enrollment_id)
        .join(Student, Student.id == ClassSession.student_id)
        .outerjoin(Instructor, Instructor.id == ClassSession.instructor_id)
        .where(ClassSession.status == SessionStatus.RESCHEDULING_REQUIRED)
        .order_by(ClassSession.scheduled_date.asc())
    )).all()
    out = []
    for sess, enr, stu, instr in rows:
        item = _serialize(sess)
        item.update({
            "student_name": stu.full_name,
            "student_cma": stu.cma_registration_id,
            "programme": enr.programme_name,
            "instructor_name": f"{instr.first_name} {instr.last_name}" if instr else None,
            "has_proposed_slot": bool(sess.preferred_date),
        })
        # any already-created replacement (pending confirmation) is surfaced too
        replacement = (await db.execute(
            select(ClassSession).where(ClassSession.replaces_session_id == sess.id)
        )).scalars().first()
        item["replacement"] = _serialize(replacement) if replacement else None
        out.append(item)
    return out


@router.get("/{session_id}")
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = await _load_session_for_write(db, current_user, session_id)
    history_result = await db.execute(
        select(SessionStatusHistory)
        .where(SessionStatusHistory.session_id == session_id)
        .order_by(SessionStatusHistory.changed_at.asc())
    )
    history = [
        {
            "from_status": h.from_status,
            "to_status": h.to_status,
            "reason": h.reason,
            "changed_at": h.changed_at.isoformat(),
        }
        for h in history_result.scalars().all()
    ]
    payload = _serialize(session)
    payload["history"] = history
    return payload


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_session(
    body: SessionCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.INSTRUCTOR])),
):
    enrollment_result = await db.execute(
        select(Enrollment).where(Enrollment.id == body.enrollment_id)
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if not enrollment.instructor_id:
        raise HTTPException(status_code=400, detail="Assign an instructor to this enrollment first")

    if current_user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, current_user)
        if not instructor or enrollment.instructor_id != instructor.id:
            raise HTTPException(status_code=403, detail="You are not assigned to this enrollment")

    scheduled_date = _parse_date(body.scheduled_date)
    start = _parse_time(body.scheduled_start)
    end = _parse_time(body.scheduled_end)
    computed_duration = _minutes_between(start, end)
    duration = body.duration_minutes or computed_duration

    if body.is_duration_exception:
        if current_user.role != UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Only admins may record duration exceptions")
        if duration < MIN_EXCEPTION_DURATION:
            raise HTTPException(status_code=400, detail=f"Exception duration must be at least {MIN_EXCEPTION_DURATION} minutes")
        if not body.exception_note:
            raise HTTPException(status_code=400, detail="An exception note is required")
    else:
        if duration < MIN_STANDARD_DURATION:
            raise HTTPException(
                status_code=400,
                detail=f"Standard sessions are at least {MIN_STANDARD_DURATION} minutes. Use an authorized duration exception otherwise.",
            )

    if not body.allow_overlap:
        clash = await _check_overlap(
            db,
            instructor_id=enrollment.instructor_id,
            student_id=enrollment.student_id,
            scheduled_date=scheduled_date,
            start=start,
            end=end,
        )
        if clash:
            who = "instructor" if clash.instructor_id == enrollment.instructor_id else "student"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Overlaps another {who} session on {clash.scheduled_date.isoformat()} "
                f"{clash.scheduled_start.strftime('%H:%M')}-{clash.scheduled_end.strftime('%H:%M')}. "
                "Set allow_overlap only if an authorized exception is intended.",
            )

    session = ClassSession(
        enrollment_id=enrollment.id,
        student_id=enrollment.student_id,
        instructor_id=enrollment.instructor_id,
        scheduled_date=scheduled_date,
        scheduled_start=start,
        scheduled_end=end,
        duration_minutes=duration,
        is_duration_exception=body.is_duration_exception,
        exception_note=body.exception_note,
        is_online=body.is_online,
        location=body.location,
        meeting_link=body.meeting_link,
        status=SessionStatus.SCHEDULED,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(session)
    await db.flush()
    await _record_history(db, session, None, SessionStatus.SCHEDULED, current_user, "Session scheduled")
    await record_audit(
        db,
        action="session.scheduled",
        entity_type="class_session",
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        after_data={"date": scheduled_date.isoformat(), "start": body.scheduled_start, "end": body.scheduled_end},
    )
    await db.flush()
    return _serialize(session)


@router.patch("/{session_id}")
async def update_session(
    session_id: UUID,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.INSTRUCTOR])),
):
    session = await _load_session_for_write(db, current_user, session_id)
    if session.status != SessionStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="Only upcoming scheduled sessions can be edited")

    scheduled_date = _parse_date(body.scheduled_date) if body.scheduled_date else session.scheduled_date
    start = _parse_time(body.scheduled_start) if body.scheduled_start else session.scheduled_start
    end = _parse_time(body.scheduled_end) if body.scheduled_end else session.scheduled_end
    duration = body.duration_minutes or _minutes_between(start, end)

    if not session.is_duration_exception and duration < MIN_STANDARD_DURATION:
        raise HTTPException(status_code=400, detail=f"Standard sessions are at least {MIN_STANDARD_DURATION} minutes")
    if session.is_duration_exception and duration < MIN_EXCEPTION_DURATION:
        raise HTTPException(status_code=400, detail=f"Exception sessions are at least {MIN_EXCEPTION_DURATION} minutes")

    if not body.allow_overlap:
        clash = await _check_overlap(
            db,
            instructor_id=session.instructor_id,
            student_id=session.student_id,
            scheduled_date=scheduled_date,
            start=start,
            end=end,
            exclude_session_id=session.id,
        )
        if clash:
            raise HTTPException(status_code=409, detail="This change overlaps another session")

    session.scheduled_date = scheduled_date
    session.scheduled_start = start
    session.scheduled_end = end
    session.duration_minutes = duration
    if body.is_online is not None:
        session.is_online = body.is_online
    if body.location is not None:
        session.location = body.location
    if body.meeting_link is not None:
        session.meeting_link = body.meeting_link
    session.updated_by = current_user.id
    await db.flush()
    await record_audit(
        db,
        action="session.edited",
        entity_type="class_session",
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
    )
    return _serialize(session)


@router.post("/{session_id}/complete")
async def complete_session(
    session_id: UUID,
    body: CompleteSession,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.INSTRUCTOR])),
):
    session = await _load_session_for_write(db, current_user, session_id)

    if session.status == SessionStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="This session is already marked completed")
    if session.status == SessionStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="A cancelled session cannot be completed")
    if session.status == SessionStatus.RESCHEDULED:
        raise HTTPException(status_code=400, detail="This class was rescheduled — complete the new dated class instead")
    if current_user.role == UserRole.INSTRUCTOR:
        if session.instructor_id != (await get_instructor_for_user(db, current_user)).id:
            raise HTTPException(status_code=403, detail="Not your assigned session")
        if session.status != SessionStatus.SCHEDULED:
            raise HTTPException(
                status_code=400,
                detail="Only scheduled classes can be marked completed (resolve reschedule requests first)",
            )

    actual_date = _parse_date(body.actual_date) if body.actual_date else session.scheduled_date
    actual_start = _parse_time(body.actual_start) if body.actual_start else session.scheduled_start
    actual_end = _parse_time(body.actual_end) if body.actual_end else session.scheduled_end
    actual_duration = body.actual_duration_minutes or _minutes_between(actual_start, actual_end)

    previous = session.status
    session.actual_date = actual_date
    session.actual_start = actual_start
    session.actual_end = actual_end
    session.actual_duration_minutes = actual_duration
    session.status = SessionStatus.COMPLETED
    session.topics_covered = body.topics_covered or session.topics_covered
    session.faculty_remarks = body.faculty_remarks or session.faculty_remarks
    session.practice_recommendations = body.practice_recommendations or session.practice_recommendations
    session.billing_month = actual_date.strftime("%Y-%m")
    session.updated_by = current_user.id

    await _record_history(
        db, session, previous, SessionStatus.COMPLETED, current_user,
        "Session completed" if actual_date == session.scheduled_date else "Rescheduled session completed",
    )
    await record_audit(
        db,
        action="session.completed",
        entity_type="class_session",
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        before_data={"status": previous},
        after_data={"status": SessionStatus.COMPLETED, "actual_date": actual_date.isoformat(), "duration": actual_duration},
    )
    await db.flush()
    return _serialize(session)


@router.post("/{session_id}/flag-reschedule")
async def flag_reschedule(
    session_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Flag that the agreed time must be moved. Never marks a student absent."""
    session = await _load_session_for_write(db, current_user, session_id)
    if session.status == SessionStatus.RESCHEDULING_REQUIRED:
        # Already requested: allow the student/instructor to update the
        # reason / proposed alternative without moving anything yet.
        reason = (body.get("reason") or "").strip()
        if not reason:
            raise HTTPException(status_code=400, detail="A reason is required")
        preferred_date = preferred_start = preferred_end = None
        if body.get("preferred_date"):
            try:
                preferred_date = _parse_date(body["preferred_date"])
                if body.get("preferred_start"):
                    preferred_start = _parse_time(body["preferred_start"])
                if body.get("preferred_end"):
                    preferred_end = _parse_time(body["preferred_end"])
                if preferred_start and preferred_end and preferred_start >= preferred_end:
                    raise ValueError("start before end")
            except Exception:
                raise HTTPException(status_code=400, detail="Proposed slot must be YYYY-MM-DD with HH:MM start before HH:MM end")
        session.reschedule_reason = reason
        session.preferred_date = preferred_date
        session.preferred_start = preferred_start
        session.preferred_end = preferred_end
        session.updated_by = current_user.id
        db.add(session)
        await record_audit(
            db,
            action="session.reschedule_proposal_updated",
            entity_type="class_session",
            entity_id=str(session.id),
            actor_user_id=current_user.id,
            actor_role=current_user.role.value,
            after_data={"reason": reason,
                        "preferred_date": preferred_date.isoformat() if preferred_date else None},
        )
        await db.flush()
        return _serialize(session)
    if session.status != SessionStatus.SCHEDULED:
        raise HTTPException(status_code=400, detail="Only scheduled sessions can be flagged")

    # 24-hour notice policy (enforced server-side; the UI disables the action)
    if _hours_until_start(session) < RESCHEDULE_NOTICE_HOURS:
        raise HTTPException(status_code=422, detail=RESCHEDULE_POLICY_TEXT)

    reason = (body.get("reason") or "").strip()
    if current_user.role in (UserRole.STUDENT, UserRole.PARENT):
        if not reason:
            raise HTTPException(status_code=400, detail="Please tell the academy why the class needs rescheduling")
    elif not reason:
        raise HTTPException(status_code=400, detail="A reason is required")

    # Optional proposed alternative slot (student preference / instructor recommendation)
    preferred_date = preferred_start = preferred_end = None
    if body.get("preferred_date"):
        try:
            preferred_date = _parse_date(body["preferred_date"])
            if body.get("preferred_start"):
                preferred_start = _parse_time(body["preferred_start"])
            if body.get("preferred_end"):
                preferred_end = _parse_time(body["preferred_end"])
            if preferred_start and preferred_end and preferred_start >= preferred_end:
                raise ValueError("start before end")
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Proposed slot must be YYYY-MM-DD with HH:MM start before HH:MM end",
            )

    previous = session.status
    session.status = SessionStatus.RESCHEDULING_REQUIRED
    session.reschedule_reason = reason
    session.preferred_date = preferred_date
    session.preferred_start = preferred_start
    session.preferred_end = preferred_end
    session.updated_by = current_user.id
    await _record_history(db, session, previous, SessionStatus.RESCHEDULING_REQUIRED, current_user, reason)
    await record_audit(
        db,
        action="session.reschedule_requested",
        entity_type="class_session",
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        after_data={
            "reason": reason,
            "preferred_date": preferred_date.isoformat() if preferred_date else None,
            "preferred_start": preferred_start.strftime("%H:%M") if preferred_start else None,
            "preferred_end": preferred_end.strftime("%H:%M") if preferred_end else None,
        },
    )
    await db.flush()
    return _serialize(session)


async def _apply_replacement(
    db: AsyncSession,
    original: ClassSession,
    new_date: date,
    start: time,
    end: time,
    duration: int,
    reason: str,
    current_user: User,
    audit_action: str = "session.rescheduled",
    policy_exception: bool = False,
) -> dict:
    """Move one dated class: keep the original record with its history and
    create the replacement occurrence. The recurring timetable is untouched."""
    previous = original.status
    original.status = SessionStatus.RESCHEDULED
    original.reschedule_reason = reason
    original.updated_by = current_user.id
    await _record_history(db, original, previous, SessionStatus.RESCHEDULED, current_user, reason)

    replacement = ClassSession(
        enrollment_id=original.enrollment_id,
        student_id=original.student_id,
        instructor_id=original.instructor_id,
        scheduled_date=new_date,
        scheduled_start=start,
        scheduled_end=end,
        duration_minutes=duration,
        status=SessionStatus.SCHEDULED,
        replaces_session_id=original.id,
        is_duration_exception=original.is_duration_exception,
        exception_note=original.exception_note,
        reschedule_reason=reason,
        is_online=original.is_online,
        location=original.location,
        meeting_link=original.meeting_link,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(replacement)
    await db.flush()
    await _record_history(db, replacement, None, SessionStatus.SCHEDULED, current_user, f"Replaces {original.scheduled_date.isoformat()} class")
    await record_audit(
        db,
        action=audit_action,
        entity_type="class_session",
        entity_id=str(replacement.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        after_data={
            "replaces": str(original.id),
            "new_date": new_date.isoformat(),
            "reason": reason,
            "policy_exception": policy_exception,
        },
    )
    await db.flush()

    # Notify the student (portal notification; no email, never any PIN)
    student = (await db.execute(select(Student).where(Student.id == original.student_id))).scalar_one_or_none()
    if student:
        await notify_user(
            db,
            user_id=student.user_id,
            type="schedule",
            title="Class rescheduled",
            body=(f"Your class on {original.scheduled_date.strftime('%d %b')} "
                  f"{original.scheduled_start.strftime('%H:%M')} was moved to "
                  f"{new_date.strftime('%d %b')} {start.strftime('%H:%M')}."),
            dedupe_key=f"resched:{replacement.id}",
            related_entity_type="class_session",
            related_entity_id=str(replacement.id),
        )
    if replacement.instructor_id:
        instr = (await db.execute(select(Instructor).where(Instructor.id == replacement.instructor_id))).scalar_one_or_none()
        if instr and instr.user_id:
            await notify_user(
                db,
                user_id=instr.user_id,
                type="schedule",
                title="Class rescheduled",
                body=(f"{student.full_name if student else 'A student'}'s class moved to "
                      f"{new_date.strftime('%d %b')} {start.strftime('%H:%M')}."),
                dedupe_key=f"resched-inst:{replacement.id}",
                related_entity_type="class_session",
                related_entity_id=str(replacement.id),
            )

    payload = _serialize(replacement)
    payload["replaced_session"] = _serialize(original)
    return payload


@router.post("/{session_id}/reschedule", status_code=status.HTTP_201_CREATED)
async def create_replacement_session(
    session_id: UUID,
    body: RescheduleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """
    Create the replacement session. The original record is retained with its
    status/history so the audit trail stays intact; the class is delivered
    once (the original never completes).
    """
    original = await _load_session_for_write(db, current_user, session_id)
    if original.status == SessionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="A completed session cannot be rescheduled")
    if original.status == SessionStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="A cancelled session cannot be rescheduled")

    # 24-hour policy: a request that was accepted (rescheduling_required) was
    # checked at submission time and can be executed at any time. An
    # admin-initiated move of a still-scheduled class needs 24 hours' notice;
    # inside that window the separate exception workflow (with reason + audit)
    # is required — the policy is never silently bypassed.
    if original.status == SessionStatus.SCHEDULED and _hours_until_start(original) < RESCHEDULE_NOTICE_HOURS:
        raise HTTPException(
            status_code=400,
            detail=RESCHEDULE_POLICY_TEXT + " For a necessary late change use the administrator "
                   "exception workflow (POST /sessions/{id}/reschedule-exception) with a reason.",
        )

    new_date = _parse_date(body.new_date)
    start = _parse_time(body.new_start)
    end = _parse_time(body.new_end)
    duration = body.duration_minutes or _minutes_between(start, end)

    if not original.is_duration_exception and duration < MIN_STANDARD_DURATION:
        raise HTTPException(status_code=400, detail=f"Standard sessions are at least {MIN_STANDARD_DURATION} minutes")

    clash = await _check_overlap(
        db,
        instructor_id=original.instructor_id,
        student_id=original.student_id,
        scheduled_date=new_date,
        start=start,
        end=end,
    )
    if clash:
        raise HTTPException(status_code=409, detail="The replacement slot overlaps another session")

    payload = await _apply_replacement(
        db, original, new_date, start, end, duration, body.reason, current_user,
        audit_action="session.rescheduled", policy_exception=False,
    )
    return payload


@router.post("/{session_id}/reschedule-exception", status_code=status.HTTP_201_CREATED)
async def reschedule_exception(
    session_id: UUID,
    body: RescheduleExceptionIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Administrator-only exception to the 24-hour notice policy.

    Use when a late change is genuinely necessary. The reason is mandatory and
    the action is recorded as `session.reschedule_exception` (policy_exception
    flag set) — the rule is never silently bypassed.
    """
    original = await _load_session_for_write(db, current_user, session_id)
    if original.status == SessionStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="A completed session cannot be rescheduled")
    if original.status == SessionStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="A cancelled session cannot be rescheduled")

    new_date = _parse_date(body.new_date)
    start = _parse_time(body.new_start)
    end = _parse_time(body.new_end)
    duration = body.duration_minutes or _minutes_between(start, end)

    if not original.is_duration_exception and duration < MIN_STANDARD_DURATION:
        raise HTTPException(status_code=400, detail=f"Standard sessions are at least {MIN_STANDARD_DURATION} minutes")

    clash = await _check_overlap(
        db,
        instructor_id=original.instructor_id,
        student_id=original.student_id,
        scheduled_date=new_date,
        start=start,
        end=end,
    )
    if clash:
        raise HTTPException(status_code=409, detail="The replacement slot overlaps another session")

    payload = await _apply_replacement(
        db, original, new_date, start, end, duration, body.reason, current_user,
        audit_action="session.reschedule_exception", policy_exception=True,
    )
    return payload


@router.post("/{session_id}/cancel")
async def cancel_session(
    session_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    session = await _load_session_for_write(db, current_user, session_id)
    if session.status in (SessionStatus.COMPLETED, SessionStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"A {session.status} session cannot be cancelled")

    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A cancellation reason is required")

    previous = session.status
    session.status = SessionStatus.CANCELLED
    session.reschedule_reason = reason
    session.updated_by = current_user.id
    await _record_history(db, session, previous, SessionStatus.CANCELLED, current_user, reason)
    await record_audit(
        db,
        action="session.cancelled",
        entity_type="class_session",
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        after_data={"reason": reason},
    )
    await db.flush()
    return _serialize(session)


@router.get("/stats/monthly")
async def monthly_session_stats(
    month: Optional[str] = None,
    student_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Counts used by dashboards: completed / scheduled / reschedule-pending."""
    month = month or date.today().strftime("%Y-%m")
    try:
        year, mon = int(month.split("-")[0]), int(month.split("-")[1])
        month_start = date(year, mon, 1)
        month_end = date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1) - timedelta(days=1)
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid month. Use YYYY-MM.")

    query = select(ClassSession.status, func.count(ClassSession.id)).where(
        ClassSession.scheduled_date >= month_start,
        ClassSession.scheduled_date <= month_end,
    )

    if current_user.role in (UserRole.STUDENT, UserRole.PARENT):
        linked = await get_linked_student_ids(db, current_user)
        query = query.where(ClassSession.student_id.in_(linked))
    elif current_user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, current_user)
        if not instructor:
            return {"month": month, "completed": 0, "scheduled": 0, "rescheduling_required": 0, "cancelled": 0}
        query = query.where(ClassSession.instructor_id == instructor.id)

    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(ClassSession.student_id == student_id)

    result = await db.execute(query.group_by(ClassSession.status))
    counts = {status_: 0 for status_ in SessionStatus.ALL}
    for status_value, count in result.all():
        counts[status_value] = count
    return {"month": month, **counts}


# ========================================
# Reschedule request queue (admin)
# ========================================
@router.post("/{session_id}/reject-reschedule")
async def reject_reschedule(
    session_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Deny a reschedule request: class stays at its original time."""
    reason = (body.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="A reason is required when rejecting a reschedule request")

    session = await _load_session_for_write(db, current_user, session_id)
    if session.status != SessionStatus.RESCHEDULING_REQUIRED:
        raise HTTPException(status_code=400, detail="This class is not awaiting a reschedule decision")

    previous = session.status
    session.status = SessionStatus.SCHEDULED      # original slot restored (it was never moved)
    session.updated_by = current_user.id
    await _record_history(db, session, previous, SessionStatus.SCHEDULED, current_user,
                          f"Reschedule request rejected: {reason}")
    await record_audit(
        db,
        action="session.reschedule_rejected",
        entity_type="class_session",
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        before_data={"status": previous},
        after_data={"status": "scheduled", "reason": reason},
    )

    student = (await db.execute(select(Student).where(Student.id == session.student_id))).scalar_one_or_none()
    if student:
        await notify_user(
            db,
            user_id=student.user_id,
            type="schedule",
            title="Reschedule request declined",
            body=(f"Your class on {session.scheduled_date.strftime('%d %b')} "
                  f"{session.scheduled_start.strftime('%H:%M')} stays at the original time. "
                  f"Reason: {reason}"),
            dedupe_key=f"resched-reject:{session.id}",
            related_entity_type="class_session",
            related_entity_id=str(session.id),
        )
    await db.flush()
    return _serialize(session)


@router.post("/{session_id}/correction")
async def correct_session_record(
    session_id: UUID,
    body: SessionCorrection,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Administrative correction of a class record (e.g. a mis-keyed completion).

    Every correction is appended to the status history and audit log; the
    original values are preserved in those trails. Re-submitting the same
    values is a no-op (idempotent).
    """
    session = await _load_session_for_write(db, current_user, session_id)

    before = {
        "actual_date": session.actual_date.isoformat() if session.actual_date else None,
        "actual_start": session.actual_start.strftime("%H:%M") if session.actual_start else None,
        "actual_end": session.actual_end.strftime("%H:%M") if session.actual_end else None,
        "actual_duration_minutes": session.actual_duration_minutes,
        "topics_covered": session.topics_covered,
        "faculty_remarks": session.faculty_remarks,
        "practice_recommendations": session.practice_recommendations,
    }

    changed = False
    if body.actual_date:
        d = _parse_date(body.actual_date)
        if session.actual_date != d:
            session.actual_date = d
            changed = True
    if body.actual_start:
        t = _parse_time(body.actual_start)
        if session.actual_start != t:
            session.actual_start = t
            changed = True
    if body.actual_end:
        t = _parse_time(body.actual_end)
        if session.actual_end != t:
            session.actual_end = t
            changed = True
    if body.actual_duration_minutes is not None and body.actual_duration_minutes != session.actual_duration_minutes:
        session.actual_duration_minutes = body.actual_duration_minutes
        changed = True
    for field in ("topics_covered", "faculty_remarks", "practice_recommendations"):
        value = getattr(body, field)
        if value is not None and value != getattr(session, field):
            setattr(session, field, value)
            changed = True

    if not changed:
        return {"id": str(session.id), "status": session.status, "changed": False}

    session.updated_by = current_user.id
    db.add(session)
    await _record_history(
        db, session, session.status, session.status, current_user,
        f"Record corrected: {body.reason}",
    )
    await record_audit(
        db,
        action="session.corrected",
        entity_type="class_session",
        entity_id=str(session.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        before_data=before,
        after_data={
            "actual_date": session.actual_date.isoformat() if session.actual_date else None,
            "topics_covered": session.topics_covered,
            "practice_recommendations": session.practice_recommendations,
            "reason": body.reason,
        },
        summary=f"Admin correction: {body.reason}",
    )
    await db.flush()
    return {"id": str(session.id), "status": session.status, "changed": True, "record": _serialize(session)}
