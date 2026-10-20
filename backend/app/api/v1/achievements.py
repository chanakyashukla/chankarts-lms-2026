"""
Student achievements showcase.

Admin creates/edits/verifies/archives records; students and their linked
parents see them in the portal; assigned instructors may view them as part
of the student's record. Nothing is exposed publicly — every route is
authenticated and scoped with the central access checks.
"""
from datetime import date as date_type
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.roles import UserRole
from app.database import get_db
from app.models.achievement import Achievement
from app.models.student import Student
from app.models.user import User
from app.services.access import require_student_access
from app.services.files import BASE_HOMEWORK_TYPES, safe_filename, save_upload, resolve_stored_file

portal_router = APIRouter()
admin_router = APIRouter()

_CATEGORIES = {"exam", "recital", "competition", "certification", "award", "milestone"}


class AchievementIn(BaseModel):
    student_id: UUID
    title: str = Field(..., min_length=2, max_length=200)
    category: str = Field(..., pattern="^(exam|recital|competition|certification|award|milestone)$")
    awarding_body: Optional[str] = None
    programme_id: Optional[str] = None
    grade_level: Optional[str] = None
    result: Optional[str] = None
    achieved_on: Optional[str] = None      # YYYY-MM-DD (historical dates allowed)
    description: Optional[str] = None


class AchievementPatch(BaseModel):
    title: Optional[str] = None
    category: Optional[str] = None
    awarding_body: Optional[str] = None
    programme_id: Optional[str] = None
    grade_level: Optional[str] = None
    result: Optional[str] = None
    achieved_on: Optional[str] = None
    description: Optional[str] = None
    is_verified: Optional[bool] = None
    is_archived: Optional[bool] = None


def _serialize(a: Achievement) -> dict:
    return {
        "id": str(a.id),
        "student_id": str(a.student_id),
        "title": a.title,
        "category": a.category,
        "awarding_body": a.awarding_body,
        "programme_id": a.programme_id,
        "grade_level": a.grade_level,
        "result": a.result,
        "achieved_on": a.achieved_on.isoformat() if a.achieved_on else None,
        "description": a.description,
        "certificate": (
            {"filename": a.cert_filename, "content_type": a.cert_content_type,
             "stored_name": a.cert_stored_name}
            if a.cert_stored_name else None
        ),
        "is_verified": bool(a.is_verified),
        "is_archived": bool(a.is_archived),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _parse_date(value: Optional[str]) -> Optional[date_type]:
    if not value:
        return None
    try:
        return date_type.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="achieved_on must be YYYY-MM-DD")


# ==================================================================
# Student / parent / instructor view — verified achievements only
# ==================================================================
@portal_router.get("/achievements")
async def list_achievements(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_student_access(db, current_user, student_id)
    rows = (await db.execute(
        select(Achievement).where(
            Achievement.student_id == student_id,
            Achievement.is_verified.is_(True),
            Achievement.is_archived.is_(False),
        ).order_by(Achievement.achieved_on.desc().nullslast(), Achievement.created_at.desc())
    )).scalars().all()
    return [_serialize(a) for a in rows]


@portal_router.get("/achievements/files/{stored_name}")
async def download_certificate(
    stored_name: str,
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_student_access(db, current_user, student_id)
    path = resolve_stored_file("achievements", stored_name)
    if path is None:
        raise HTTPException(status_code=404, detail="Certificate not found")
    return FileResponse(path)


# ==================================================================
# Admin management
# ==================================================================
@admin_router.get("/achievements")
async def admin_list_achievements(
    student_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    query = select(Achievement).order_by(Achievement.achieved_on.desc().nullslast(), Achievement.created_at.desc())
    if student_id:
        query = query.where(Achievement.student_id == student_id)
    rows = (await db.execute(query)).scalars().all()
    out = []
    for a in rows:
        payload = _serialize(a)
        st = (await db.execute(select(Student).where(Student.id == a.student_id))).scalar_one_or_none()
        payload["student_name"] = st.full_name if st else None
        out.append(payload)
    return out


@admin_router.post("/achievements", status_code=status.HTTP_201_CREATED)
async def admin_create_achievement(
    body: AchievementIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    student = (await db.execute(select(Student).where(Student.id == body.student_id))).scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    a = Achievement(
        student_id=body.student_id,
        title=body.title.strip(),
        category=body.category,
        awarding_body=body.awarding_body,
        programme_id=body.programme_id,
        grade_level=body.grade_level,
        result=body.result,
        achieved_on=_parse_date(body.achieved_on),
        description=body.description,
        created_by=current_user.id,
        is_verified=False,
    )
    db.add(a)
    await db.flush()
    return _serialize(a)


@admin_router.post("/achievements/{achievement_id}/certificate", status_code=status.HTTP_201_CREATED)
async def admin_upload_certificate(
    achievement_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    a = (await db.execute(select(Achievement).where(Achievement.id == achievement_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Achievement not found")
    stored_name, content_type, size, _ = await save_upload(
        file, subdir="achievements", allowed_types=BASE_HOMEWORK_TYPES
    )
    a.cert_stored_name = stored_name
    a.cert_filename = safe_filename(file.filename)
    a.cert_content_type = content_type
    db.add(a)
    await db.flush()
    return {"id": str(a.id), "filename": a.cert_filename}


@admin_router.patch("/achievements/{achievement_id}")
async def admin_patch_achievement(
    achievement_id: UUID,
    body: AchievementPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    """Edit, verify (publish to the student) or archive an achievement."""
    a = (await db.execute(select(Achievement).where(Achievement.id == achievement_id))).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="Achievement not found")
    for field in ("title", "category", "awarding_body", "programme_id", "grade_level",
                  "result", "description"):
        value = getattr(body, field)
        if value is not None:
            setattr(a, field, value)
    if body.achieved_on is not None:
        a.achieved_on = _parse_date(body.achieved_on)
    if body.is_verified is not None:
        a.is_verified = body.is_verified
    if body.is_archived is not None:
        a.is_archived = body.is_archived
    db.add(a)
    await db.flush()
    return _serialize(a)
