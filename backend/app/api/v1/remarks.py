"""
Additional student remarks with explicit visibility.

There is no default visibility: staff must choose staff_only, student_visible
or parent_visible. Staff-only remarks are never serialized to student/parent
responses, reports, downloads or any other channel. Every create/edit is
audited.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.roles import UserRole
from app.database import get_db
from app.models.remark import StudentRemark, RemarkVisibility
from app.models.student import Student
from app.models.user import User
from app.services.access import (
    get_linked_student_ids,
    get_instructor_for_user,
    require_student_access,
)
from app.services.audit import record_audit

router = APIRouter()

STAFF_ROLES = (UserRole.ADMIN, UserRole.INSTRUCTOR)


def _is_staff(user: User) -> bool:
    return user.role in STAFF_ROLES


def _serialize_remark(r: StudentRemark, include_staff: bool = False) -> dict:
    payload = {
        "id": str(r.id),
        "student_id": str(r.student_id),
        "enrollment_id": str(r.enrollment_id) if r.enrollment_id else None,
        "visibility": r.visibility,
        "body": r.body,
        "author_role": r.author_role,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
    # staff_only remarks are only ever returned to staff, and even then the
    # caller must explicitly request them via the staff listing endpoint.
    return payload


class RemarkCreate(BaseModel):
    student_id: UUID
    enrollment_id: Optional[UUID] = None
    visibility: str = Field(..., pattern="^(staff_only|student_visible|parent_visible)$")
    body: str = Field(..., min_length=1, max_length=5000)


class RemarkUpdate(BaseModel):
    visibility: Optional[str] = Field(None, pattern="^(staff_only|student_visible|parent_visible)$")
    body: Optional[str] = Field(None, min_length=1, max_length=5000)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_remark(
    body: RemarkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(list(STAFF_ROLES))),
):
    await require_student_access(db, current_user, body.student_id)

    if current_user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, current_user)
        if not instructor:
            raise HTTPException(status_code=403, detail="Instructor profile not found")
        # Instructors may only remark on students they actually teach
        from sqlalchemy import select as _select
        from app.models.enrollment import Enrollment

        result = await db.execute(
            _select(Enrollment.id).where(
                Enrollment.student_id == body.student_id,
                Enrollment.instructor_id == instructor.id,
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(status_code=403, detail="You do not teach this student")

    remark = StudentRemark(
        student_id=body.student_id,
        enrollment_id=body.enrollment_id,
        author_user_id=current_user.id,
        author_role=current_user.role.value,
        visibility=body.visibility,
        body=body.body,
    )
    db.add(remark)
    await db.flush()

    await record_audit(
        db,
        action="remark.created",
        entity_type="student_remark",
        entity_id=str(remark.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"visibility={remark.visibility}",
        after_data={"visibility": remark.visibility, "body": remark.body},
    )
    await db.commit()
    return _serialize_remark(remark)


@router.get("")
async def list_remarks(
    student_id: UUID,
    include_staff_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List remarks for a student, scoped to what the caller is allowed to see.

    - staff: all remarks, including staff_only (staff_only only when
      include_staff_only=true, so a UI can opt in explicitly)
    - student: only student_visible, and only for their own student_id
    - parent: only parent_visible, and only for explicitly linked children
    """
    await require_student_access(db, current_user, student_id)

    query = select(StudentRemark).where(StudentRemark.student_id == student_id)

    if _is_staff(current_user):
        if not include_staff_only:
            query = query.where(StudentRemark.visibility != RemarkVisibility.STAFF_ONLY)
    elif current_user.role == UserRole.STUDENT:
        query = query.where(StudentRemark.visibility == RemarkVisibility.STUDENT_VISIBLE)
    elif current_user.role == UserRole.PARENT:
        query = query.where(StudentRemark.visibility == RemarkVisibility.PARENT_VISIBLE)
    else:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    query = query.order_by(StudentRemark.created_at.desc())
    result = await db.execute(query)
    return [_serialize_remark(r) for r in result.scalars().all()]


@router.patch("/{remark_id}")
async def update_remark(
    remark_id: UUID,
    body: RemarkUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(list(STAFF_ROLES))),
):
    result = await db.execute(select(StudentRemark).where(StudentRemark.id == remark_id))
    remark = result.scalar_one_or_none()
    if not remark:
        raise HTTPException(status_code=404, detail="Remark not found")

    await require_student_access(db, current_user, remark.student_id)
    if current_user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, current_user)
        if not instructor or remark.author_user_id != current_user.id:
            # An instructor may only edit their own remarks
            raise HTTPException(status_code=403, detail="You may only edit your own remarks")

    before = {"visibility": remark.visibility, "body": remark.body}
    if body.visibility is not None:
        remark.visibility = body.visibility
    if body.body is not None:
        remark.body = body.body
    remark.updated_at = remark.updated_at  # touch

    await record_audit(
        db,
        action="remark.updated",
        entity_type="student_remark",
        entity_id=str(remark.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        summary=f"visibility {before['visibility']} -> {remark.visibility}",
        before_data=before,
        after_data={"visibility": remark.visibility, "body": remark.body},
    )
    await db.commit()
    return _serialize_remark(remark)


@router.get("/{remark_id}/history")
async def remark_history(
    remark_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(list(STAFF_ROLES))),
):
    """Audit trail (create + edits) for a remark, staff only."""
    from app.models.audit import AuditEvent

    result = await db.execute(select(StudentRemark).where(StudentRemark.id == remark_id))
    remark = result.scalar_one_or_none()
    if not remark:
        raise HTTPException(status_code=404, detail="Remark not found")
    await require_student_access(db, current_user, remark.student_id)

    events = await db.execute(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "student_remark",
            AuditEvent.entity_id == str(remark_id),
        )
        .order_by(AuditEvent.created_at.asc())
    )
    return [
        {
            "id": str(e.id),
            "action": e.action,
            "actor_role": e.actor_role,
            "summary": e.summary,
            "before_data": e.before_data,
            "after_data": e.after_data,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events.scalars().all()
    ]
