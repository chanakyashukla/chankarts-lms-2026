"""
Learning modules: assignments + submissions, study materials, syllabus progress,
monthly faculty reports, exams/milestones and recommended resources.
"""
import datetime as dt
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.roles import UserRole
from app.database import get_db
from app.models.enrollment import Enrollment
from app.models.exam import Exam, ExamItem, Milestone
from app.models.learning import (
    ResourceVisibilityTarget,
    Assignment,
    AssignmentFile,
    MaterialAssignment,
    ResourceRecommendation,
    StudyMaterial,
    Submission,
)
from app.models.reports import MonthlyReport
from app.models.session import ClassSession
from app.models.student import Student
from app.models.syllabus import StudentSyllabusAssignment, StudentSyllabusProgress, Syllabus, SyllabusItem
from app.models.user import User
from app.services.access import (
    get_instructor_for_user,
    get_linked_student_ids,
    require_student_access,
)
from app.services.audit import record_audit
from app.services.files import (
    AUDIO_TYPES,
    BASE_HOMEWORK_TYPES,
    resolve_stored_file,
    safe_filename,
    save_upload,
)

router = APIRouter()


def _is_staff(user: User) -> bool:
    return user.role in (UserRole.ADMIN, UserRole.INSTRUCTOR)


async def _require_staff(db: AsyncSession, user: User) -> None:
    if not _is_staff(user):
        raise HTTPException(status_code=403, detail="Faculty or admin access required")


async def _accessible_student_ids(db: AsyncSession, user: User) -> Optional[List[UUID]]:
    """None = unrestricted (admin). List = allowed students. [] = none."""
    if user.role == UserRole.ADMIN:
        return None
    if user.role in (UserRole.STUDENT, UserRole.PARENT):
        return await get_linked_student_ids(db, user)
    if user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, user)
        if not instructor:
            return []
        result = await db.execute(
            select(Enrollment.student_id).where(Enrollment.instructor_id == instructor.id).distinct()
        )
        return list(result.scalars().all())
    return []


# ==================================================================
# Assignments
# ==================================================================
class AssignmentCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    instructions: Optional[str] = None
    practice_notes: Optional[str] = None
    enrollment_id: UUID
    assigned_date: Optional[str] = None
    due_date: Optional[str] = None
    priority: str = Field("normal", pattern="^(low|normal|high)$")
    allow_audio: bool = False


class AssignmentReview(BaseModel):
    feedback: str = Field(..., min_length=1)
    status: str = Field(..., pattern="^(reviewed|revision_requested)$")


def _serialize_assignment(a: Assignment, submission: Optional[Submission] = None) -> dict:
    return {
        "id": str(a.id),
        "title": a.title,
        "instructions": a.instructions,
        "practice_notes": a.practice_notes,
        "enrollment_id": str(a.enrollment_id),
        "student_id": str(a.student_id),
        "created_by": str(a.created_by) if a.created_by else None,
        "assigned_date": a.assigned_date.isoformat() if a.assigned_date else None,
        "due_date": a.due_date.isoformat() if a.due_date else None,
        "priority": a.priority,
        "status": a.status,
        "allow_audio": a.allow_audio,
        "submission": (
            {
                "id": str(submission.id),
                "status": submission.status,
                "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
                "feedback": submission.feedback,
                "reviewed_at": submission.reviewed_at.isoformat() if submission.reviewed_at else None,
                "attempt_number": submission.attempt_number,
                "notes": submission.notes,
            }
            if submission
            else None
        ),
    }


@router.get("/assignments")
async def list_assignments(
    student_id: Optional[UUID] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    limit: int = Query(100, le=300),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Assignment)

    allowed = await _accessible_student_ids(db, current_user)
    if allowed is not None:
        if not allowed:
            return []
        query = query.where(Assignment.student_id.in_(allowed))
    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(Assignment.student_id == student_id)
    if status_filter:
        query = query.where(Assignment.status == status_filter)

    query = query.order_by(Assignment.due_date.asc().nullslast()).limit(limit)
    result = await db.execute(query)
    assignments = list(result.scalars().all())

    submissions_by_assignment = {}
    if assignments:
        sub_result = await db.execute(
            select(Submission).where(Submission.assignment_id.in_([a.id for a in assignments]))
        )
        for submission in sub_result.scalars().all():
            current = submissions_by_assignment.get(submission.assignment_id)
            if current is None or submission.attempt_number > current.attempt_number:
                submissions_by_assignment[submission.assignment_id] = submission

    return [
        _serialize_assignment(a, submissions_by_assignment.get(a.id))
        for a in assignments
    ]


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
async def create_assignment(
    body: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    enrollment_result = await db.execute(
        select(Enrollment).where(Enrollment.id == body.enrollment_id)
    )
    enrollment = enrollment_result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")

    if current_user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, current_user)
        if not instructor or enrollment.instructor_id != instructor.id:
            raise HTTPException(status_code=403, detail="You are not assigned to this enrollment")

    # Prevent accidental duplicates: same title on the same enrolment while
    # still open (assigned/submitted/revision_requested) is refused.
    open_dup = await db.execute(
        select(Assignment).where(
            Assignment.enrollment_id == enrollment.id,
            Assignment.title == body.title,
            Assignment.status.in_(["assigned", "submitted", "revision_requested"]),
        )
    )
    if open_dup.scalars().first():
        raise HTTPException(
            status_code=409,
            detail="An open assignment with this title already exists for this enrolment",
        )

    assignment = Assignment(
        title=body.title,
        instructions=body.instructions,
        practice_notes=body.practice_notes,
        enrollment_id=enrollment.id,
        student_id=enrollment.student_id,
        created_by=current_user.id,
        assigned_date=dt.date.fromisoformat(body.assigned_date) if body.assigned_date else dt.date.today(),
        due_date=dt.date.fromisoformat(body.due_date) if body.due_date else None,
        priority=body.priority,
        allow_audio=body.allow_audio,
    )
    db.add(assignment)
    await db.flush()
    await record_audit(
        db,
        action="assignment.created",
        entity_type="assignment",
        entity_id=str(assignment.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        after_data={"title": body.title, "student_id": str(enrollment.student_id)},
    )
    return _serialize_assignment(assignment)


@router.post("/assignments/{assignment_id}/files", status_code=status.HTTP_201_CREATED)
async def attach_assignment_file(
    assignment_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Faculty attaches reference material (brief) to an assignment."""
    await _require_staff(db, current_user)
    result = await db.execute(select(Assignment).where(Assignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    stored_name, content_type, size, digest = await save_upload(
        file, subdir="assignment_briefs", allowed_types=BASE_HOMEWORK_TYPES
    )
    row = AssignmentFile(
        assignment_id=assignment.id,
        owner_user_id=current_user.id,
        owner_role="faculty",
        filename=safe_filename(file.filename),
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=size,
        sha256=digest,
    )
    db.add(row)
    await db.flush()
    return {"id": str(row.id), "filename": row.filename, "content_type": content_type, "size_bytes": size}


@router.post("/assignments/{assignment_id}/submit", status_code=status.HTTP_201_CREATED)
async def submit_homework(
    assignment_id: UUID,
    notes: Optional[str] = Form(None),
    files: List[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Student uploads homework (PDF/image, audio when the assignment allows it)."""
    if current_user.role != UserRole.STUDENT:
        raise HTTPException(status_code=403, detail="Only students can submit homework")

    result = await db.execute(select(Assignment).where(Assignment.id == assignment_id))
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    student_result = await db.execute(select(Student).where(Student.user_id == current_user.id))
    student = student_result.scalar_one_or_none()
    if not student or student.id != assignment.student_id:
        raise HTTPException(status_code=403, detail="This assignment is not yours")

    allowed_types = set(BASE_HOMEWORK_TYPES)
    if assignment.allow_audio:
        allowed_types |= AUDIO_TYPES

    attempt_result = await db.execute(
        select(Submission).where(Submission.assignment_id == assignment.id)
    )
    attempts = attempt_result.scalars().all()
    attempt_number = (max((s.attempt_number for s in attempts), default=0)) + 1

    submission = Submission(
        assignment_id=assignment.id,
        student_id=student.id,
        attempt_number=attempt_number,
        notes=notes,
        status="submitted",
    )
    db.add(submission)
    await db.flush()

    uploaded = []
    for upload in files:
        if not upload or not upload.filename:
            continue
        stored_name, content_type, size, digest = await save_upload(
            upload, subdir="homework", allowed_types=allowed_types
        )
        row = AssignmentFile(
            assignment_id=assignment.id,
            submission_id=submission.id,
            owner_user_id=current_user.id,
            owner_role="student",
            filename=safe_filename(upload.filename),
            stored_name=stored_name,
            content_type=content_type,
            size_bytes=size,
            sha256=digest,
        )
        db.add(row)
        uploaded.append({"filename": row.filename, "content_type": content_type, "size_bytes": size})

    assignment.status = "submitted"
    await db.flush()
    return {"submission_id": str(submission.id), "attempt_number": attempt_number, "files": uploaded}


@router.post("/submissions/{submission_id}/review")
async def review_submission(
    submission_id: UUID,
    body: AssignmentReview,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    result = await db.execute(select(Submission).where(Submission.id == submission_id))
    submission = result.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    submission.feedback = body.feedback
    submission.status = body.status
    submission.reviewed_by = current_user.id
    submission.reviewed_at = dt.datetime.utcnow()

    assignment_result = await db.execute(
        select(Assignment).where(Assignment.id == submission.assignment_id)
    )
    assignment = assignment_result.scalar_one_or_none()
    if assignment:
        assignment.status = body.status
    await db.flush()
    return {"submission_id": str(submission.id), "status": submission.status}


@router.get("/files/{stored_name}")
async def download_file(
    stored_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Authorized download of an uploaded file (never publicly served)."""
    for subdir in ("homework", "assignment_briefs", "materials"):
        path = resolve_stored_file(subdir, stored_name)
        if not path:
            continue

        if _is_staff(current_user):
            return FileResponse(path, filename=path.name)

        allowed = await _accessible_student_ids(db, current_user)
        allowed = allowed or []

        if subdir == "homework":
            row_result = await db.execute(
                select(AssignmentFile).where(AssignmentFile.stored_name == stored_name)
            )
            row = row_result.scalar_one_or_none()
            if row and row.owner_user_id == current_user.id:
                return FileResponse(path, filename=path.name)
            if row:
                assignment_result = await db.execute(
                    select(Assignment).where(Assignment.id == row.assignment_id)
                )
                assignment = assignment_result.scalar_one_or_none()
                if assignment and assignment.student_id in allowed:
                    return FileResponse(path, filename=path.name)
            raise HTTPException(status_code=403, detail="Access denied")

        if subdir == "assignment_briefs":
            row_result = await db.execute(
                select(AssignmentFile).where(AssignmentFile.stored_name == stored_name)
            )
            row = row_result.scalar_one_or_none()
            if row:
                assignment_result = await db.execute(
                    select(Assignment).where(Assignment.id == row.assignment_id)
                )
                assignment = assignment_result.scalar_one_or_none()
                if assignment and assignment.student_id in allowed:
                    return FileResponse(path, filename=path.name)
            raise HTTPException(status_code=403, detail="Access denied")

        # materials
        material_result = await db.execute(
            select(StudyMaterial).where(StudyMaterial.stored_name == stored_name)
        )
        material = material_result.scalar_one_or_none()
        if not material:
            raise HTTPException(status_code=404, detail="File not found")
        assigned = await db.execute(
            select(MaterialAssignment).where(
                MaterialAssignment.material_id == material.id,
                MaterialAssignment.student_id.in_(allowed or []),
            )
        )
        material_ok = (
            material.programme_id is None and material.is_published
        ) or assigned.scalars().first() is not None
        if material_ok or material.programme_id is None:
            return FileResponse(path, filename=material.filename or path.name)
        raise HTTPException(status_code=403, detail="Access denied")

    raise HTTPException(status_code=404, detail="File not found")


# ==================================================================
# Study materials
# ==================================================================
class MaterialCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: Optional[str] = None
    category: str = Field(..., pattern="^(technique|repertoire|theory|ear_training|rhythm|exam_preparation|practice)$")
    programme_id: Optional[str] = None
    level: Optional[str] = None
    link_url: Optional[str] = None


def _split_ids(value: Optional[str]) -> list:
    out = []
    for part in (value or "").replace(",", " ").split():
        try:
            out.append(UUID(part.strip()))
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid student id: {part}")
    return out


_SKILL_LEVELS = {"beginner", "intermediate", "advanced"}
_VALID_SCOPES = {"all", "students", "programme", "level"}


def _parse_scope(value: Optional[str]) -> str:
    scope = (value or "all").strip().lower()
    if scope not in _VALID_SCOPES:
        raise HTTPException(status_code=400, detail="visibility_scope must be all, students, programme or level")
    return scope


async def _target_student_ids(db: AsyncSession, kind: str, resource_id) -> set:
    rows = (await db.execute(
        select(ResourceVisibilityTarget.student_id).where(
            ResourceVisibilityTarget.resource_kind == kind,
            ResourceVisibilityTarget.resource_id == resource_id,
        ))).scalars().all()
    return set(rows)


async def _audience_allows(
    db: AsyncSession,
    *,
    kind: str,
    resource_id,
    scope: str,
    programme_id: Optional[str],
    level: Optional[str],
    student_ids: list,
) -> bool:
    """True when at least one of student_ids is in the resource's audience.

    Audience rules (unambiguous, enforced server-side):
      all        -> every active student
      students   -> only explicitly targeted students
      programme  -> students with an active enrolment in programme_id
                    (a beginner/intermediate/advanced level adds an AND filter)
      level      -> students whose skill level matches
    An explicit target row always grants access on top of the scope base.
    """
    if not student_ids:
        return False
    if scope == "all":
        return True
    if resource_id is not None:
        targeted = await _target_student_ids(db, kind, resource_id)
        if targeted & set(student_ids):
            return True
    if scope == "students":
        return False
    if scope == "programme" and programme_id:
        q = (
            select(Student.id)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(
                Enrollment.programme_id == programme_id,
                Enrollment.status == "active",
                Student.id.in_(student_ids),
                Student.status == "active",
            )
        )
        if (level or "").lower() in _SKILL_LEVELS:
            q = q.where(Student.skill_level == level.lower())
        found = (await db.execute(q.limit(1))).scalars().first()
        return found is not None
    if scope == "level" and (level or "").lower() in _SKILL_LEVELS:
        found = (await db.execute(
            select(Student.id).where(
                Student.id.in_(student_ids),
                Student.status == "active",
                Student.skill_level == level.lower(),
            ).limit(1))).scalars().first()
        return found is not None
    return False


async def _audience_student_ids_for_user(db: AsyncSession, current_user: User) -> Optional[list]:
    """Candidate student ids for the current viewer (None = unrestricted admin)."""
    if current_user.role == UserRole.ADMIN:
        return None
    allowed = await _accessible_student_ids(db, current_user)
    return list(allowed or [])


@router.get("/materials")
async def list_materials(
    category: Optional[str] = None,
    programme_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidates = await _audience_student_ids_for_user(db, current_user)

    query = select(StudyMaterial).where(StudyMaterial.is_published.is_(True))
    if category:
        query = query.where(StudyMaterial.category == category)
    if programme_id:
        query = query.where(StudyMaterial.programme_id == programme_id)

    result = await db.execute(query.order_by(StudyMaterial.created_at.desc()))

    out = []
    for m in result.scalars().all():
        # Admin manages everything; everyone else sees only their audience.
        if candidates is not None:
            ok = await _audience_allows(
                db, kind="material", resource_id=m.id,
                scope=m.visibility_scope or "all",
                programme_id=m.programme_id, level=m.level,
                student_ids=candidates,
            )
            if not ok:
                continue
        out.append(
            {
                "id": str(m.id),
                "title": m.title,
                "description": m.description,
                "category": m.category,
                "programme_id": m.programme_id,
                "level": m.level,
                "visibility_scope": m.visibility_scope or "all",
                "material_type": m.material_type,
                "filename": m.filename,
                "stored_name": m.stored_name,
                "link_url": m.link_url,
                "size_bytes": m.size_bytes,
                "content_type": m.content_type,
                "version": m.version,
            }
        )
    return out


@router.post("/materials", status_code=status.HTTP_201_CREATED)
async def create_material(
    title: str = Form(...),
    category: str = Form(...),
    description: Optional[str] = Form(None),
    programme_id: Optional[str] = Form(None),
    level: Optional[str] = Form(None),
    link_url: Optional[str] = Form(None),
    visibility_scope: Optional[str] = Form("all"),
    target_student_ids: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)

    stored_name = filename = content_type = None
    size = None
    material_type = "link"
    if file and file.filename:
        stored_name, content_type, size, _ = await save_upload(
            file, subdir="materials", allowed_types=BASE_HOMEWORK_TYPES | AUDIO_TYPES
        )
        filename = safe_filename(file.filename)
        material_type = "file"
    elif link_url:
        material_type = "link"
    else:
        raise HTTPException(status_code=400, detail="Provide a file or an external link")

    scope = _parse_scope(visibility_scope)
    if scope == "programme" and not (programme_id or None):
        raise HTTPException(status_code=400, detail="visibility_scope=programme needs a programme_id")
    if scope == "level" and not (level or None):
        raise HTTPException(status_code=400, detail="visibility_scope=level needs a level")

    material = StudyMaterial(
        title=title,
        description=description,
        category=category,
        programme_id=programme_id or None,
        level=level,
        visibility_scope=scope,
        material_type=material_type,
        stored_name=stored_name,
        filename=filename,
        content_type=content_type,
        size_bytes=size,
        link_url=link_url,
        created_by=current_user.id,
    )
    db.add(material)
    await db.flush()
    targets = 0
    for sid in _split_ids(target_student_ids):
        if not (await db.execute(select(Student).where(Student.id == sid))).scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Unknown student {sid}")
        db.add(ResourceVisibilityTarget(
            resource_kind="material", resource_id=material.id, student_id=sid,
            created_by=current_user.id))
        targets += 1
    await db.flush()
    return {"id": str(material.id), "title": material.title,
            "material_type": material_type, "visibility_scope": scope,
            "target_students": targets}


@router.post("/materials/{material_id}/assign", status_code=status.HTTP_201_CREATED)
async def assign_material(
    material_id: UUID,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    student_id = body.get("student_id")
    if not student_id:
        raise HTTPException(status_code=400, detail="student_id is required")
    material_result = await db.execute(select(StudyMaterial).where(StudyMaterial.id == material_id))
    if not material_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Material not found")
    student_result = await db.execute(select(Student).where(Student.id == UUID(student_id)))
    if not student_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Student not found")

    row = MaterialAssignment(
        material_id=material_id,
        student_id=UUID(student_id),
        enrollment_id=UUID(body["enrollment_id"]) if body.get("enrollment_id") else None,
        assigned_by=current_user.id,
    )
    db.add(row)
    # keep the unified visibility targeting in step with legacy assignments
    existing_target = (await db.execute(
        select(ResourceVisibilityTarget).where(
            ResourceVisibilityTarget.resource_kind == "material",
            ResourceVisibilityTarget.resource_id == material_id,
            ResourceVisibilityTarget.student_id == UUID(student_id),
        ))).scalar_one_or_none()
    if not existing_target:
        db.add(ResourceVisibilityTarget(
            resource_kind="material", resource_id=material_id,
            student_id=UUID(student_id), created_by=current_user.id))
    await db.flush()
    return {"id": str(row.id)}


# ==================================================================
# Monthly reports
# ==================================================================
REPORT_FIELDS = (
    "progress_summary",
    "topics_covered",
    "skills_demonstrated",
    "strengths",
    "areas_for_improvement",
    "practice_recommendations",
    "assignment_status",
    "syllabus_progress",
    "exam_preparation",
    "next_month_focus",
    "faculty_remarks",
)


class ReportCreate(BaseModel):
    student_id: UUID
    enrollment_id: UUID
    report_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    progress_summary: Optional[str] = None
    topics_covered: Optional[str] = None
    skills_demonstrated: Optional[str] = None
    strengths: Optional[str] = None
    areas_for_improvement: Optional[str] = None
    practice_recommendations: Optional[str] = None
    assignment_status: Optional[str] = None
    syllabus_progress: Optional[str] = None
    exam_preparation: Optional[str] = None
    next_month_focus: Optional[str] = None
    faculty_remarks: Optional[str] = None
    staff_notes: Optional[str] = None


def _serialize_report(r: MonthlyReport, include_staff: bool) -> dict:
    payload = {
        "id": str(r.id),
        "student_id": str(r.student_id),
        "enrollment_id": str(r.enrollment_id),
        "instructor_id": str(r.instructor_id) if r.instructor_id else None,
        "report_month": r.report_month,
        "revision": r.revision,
        "status": r.status,
        "published_at": r.published_at.isoformat() if r.published_at else None,
    }
    for field in REPORT_FIELDS:
        payload[field] = getattr(r, field)
    if include_staff:
        payload["staff_notes"] = r.staff_notes
    return payload


class ReportGenerateIn(BaseModel):
    """Generate/refresh a monthly report draft from actual class records."""
    enrollment_id: UUID
    report_month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    confirm_overwrite: bool = False


# Fields derived from class records (safe to regenerate)
AUTO_REPORT_FIELDS = ("progress_summary", "topics_covered", "practice_recommendations")
NOT_RECORDED = "[no lesson note recorded for this class]"


def _month_window(report_month: str):
    year, month = (int(x) for x in report_month.split("-"))
    import calendar
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    return first, last


@router.post("/reports/generate-draft", status_code=status.HTTP_201_CREATED)
async def generate_report_draft(
    body: ReportGenerateIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Prepare a monthly report draft from the class-completion records.

    Only what the class records actually contain is summarised — missing
    lesson notes are shown as missing, never invented. Instructor-written
    fields (observations, achievements, concerns, recommendations) are never
    touched by generation. Regenerating never silently overwrites an existing
    draft or a submitted report: pass confirm_overwrite=true explicitly.
    """
    await _require_staff(db, current_user)

    enrollment = (await db.execute(
        select(Enrollment).where(Enrollment.id == body.enrollment_id))).scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrolment not found")
    instructor = await get_instructor_for_user(db, current_user)
    if instructor and enrollment.instructor_id and enrollment.instructor_id != instructor.id:
        raise HTTPException(status_code=403, detail="You are not assigned to this enrolment")

    first, last = _month_window(body.report_month)
    rows = (await db.execute(
        select(ClassSession)
        .where(
            ClassSession.enrollment_id == enrollment.id,
            ClassSession.scheduled_date >= first,
            ClassSession.scheduled_date <= last,
            ClassSession.status.in_(("completed", "scheduled", "rescheduling_required", "rescheduled", "cancelled")),
        )
        .order_by(ClassSession.scheduled_date.asc(), ClassSession.scheduled_start.asc())
    )).scalars().all()
    completed = [r for r in rows if r.status == "completed"]
    deliverable = [r for r in rows if r.status in ("completed", "scheduled", "rescheduling_required", "rescheduled")]

    # ---- build derived content strictly from records ----
    if completed:
        topic_lines = []
        practice_lines = []
        for r in completed:
            note = (r.topics_covered or "").strip() or NOT_RECORDED
            topic_lines.append(f"{r.scheduled_date.strftime('%d %b')} — {note}")
            prac = (r.practice_recommendations or "").strip()
            if prac:
                practice_lines.append(f"{r.scheduled_date.strftime('%d %b')} — {prac}")
        topics_covered = "\n".join(topic_lines)
        practice_recommendations = ("\n".join(practice_lines) if practice_lines
                                    else "[no practice recommendations recorded]")
        progress_summary = (
            f"{len(completed)} of {len(deliverable)} scheduled classes completed in {body.report_month}. "
            f"Lesson notes recorded for "
            f"{sum(1 for r in completed if (r.topics_covered or '').strip())} of {len(completed)} completed classes."
        )
    else:
        topics_covered = "[no completed classes recorded for this month]"
        practice_recommendations = "[no practice recommendations recorded]"
        progress_summary = f"[no completed class records for {body.report_month}]"

    # ---- find or create the report row ----
    latest = (await db.execute(
        select(MonthlyReport)
        .where(MonthlyReport.enrollment_id == enrollment.id,
               MonthlyReport.report_month == body.report_month)
        .order_by(MonthlyReport.revision.desc())
    )).scalars().first()

    created_new = False
    if latest and latest.status == "published":
        # published content is immutable — the regeneration becomes a new revision
        report = MonthlyReport(
            student_id=latest.student_id,
            enrollment_id=latest.enrollment_id,
            instructor_id=latest.instructor_id,
            report_month=body.report_month,
            revision=latest.revision + 1,
            previous_revision_id=latest.id,
            status="draft",
            created_by=current_user.id,
            staff_notes=latest.staff_notes,
        )
        for field in REPORT_FIELDS:
            if field not in AUTO_REPORT_FIELDS:
                setattr(report, field, getattr(latest, field))
        created_new = True
        db.add(report)
    elif latest and not body.confirm_overwrite:
        raise HTTPException(
            status_code=409,
            detail=f"A {latest.status} report already exists for {body.report_month}. "
                   "Pass confirm_overwrite=true to regenerate the draft from class records "
                   "(instructor-written fields are kept).",
        )
    elif latest:
        report = latest
        if report.status == "submitted":
            report.status = "draft"   # regeneration returns it to draft for review
    else:
        report = MonthlyReport(
            student_id=enrollment.student_id,
            enrollment_id=enrollment.id,
            report_month=body.report_month,
            revision=1,
            status="draft",
            created_by=current_user.id,
        )
        created_new = True
        db.add(report)

    if instructor:
        report.instructor_id = instructor.id
    report.progress_summary = progress_summary
    report.topics_covered = topics_covered
    report.practice_recommendations = practice_recommendations
    report.created_by = report.created_by or current_user.id
    await db.flush()
    payload = _serialize_report(report, include_staff=True)
    payload["generated_from_sessions"] = {
        "completed": len(completed),
        "deliverable": len(deliverable),
        "cancelled": sum(1 for r in rows if r.status == "cancelled"),
        "missing_lesson_notes": sum(1 for r in completed if not (r.topics_covered or "").strip()),
    }
    payload["created_new"] = created_new
    return payload


@router.get("/reports")
async def list_reports(
    student_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(MonthlyReport)
    allowed = await _accessible_student_ids(db, current_user)
    if allowed is not None:
        if not allowed:
            return []
        query = query.where(MonthlyReport.student_id.in_(allowed))
        if not _is_staff(current_user):
            query = query.where(MonthlyReport.status == "published")
    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(MonthlyReport.student_id == student_id)

    query = query.order_by(MonthlyReport.report_month.desc(), MonthlyReport.revision.desc())
    result = await db.execute(query)
    include_staff = _is_staff(current_user)
    return [_serialize_report(r, include_staff) for r in result.scalars().all()]


@router.post("/reports", status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    existing = await db.execute(
        select(MonthlyReport).where(
            MonthlyReport.enrollment_id == body.enrollment_id,
            MonthlyReport.report_month == body.report_month,
        ).order_by(MonthlyReport.revision.desc())
    )
    latest = existing.scalars().first()

    report = MonthlyReport(
        student_id=body.student_id,
        enrollment_id=body.enrollment_id,
        report_month=body.report_month,
        revision=(latest.revision + 1) if latest else 1,
        previous_revision_id=latest.id if latest else None,
        status="draft",
        created_by=current_user.id,
        staff_notes=body.staff_notes,
    )
    for field in REPORT_FIELDS:
        setattr(report, field, getattr(body, field))

    instructor = await get_instructor_for_user(db, current_user)
    if instructor:
        report.instructor_id = instructor.id

    db.add(report)
    await db.flush()
    return _serialize_report(report, include_staff=True)


@router.patch("/reports/{report_id}")
async def update_report(
    report_id: UUID,
    body: ReportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    result = await db.execute(select(MonthlyReport).where(MonthlyReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.status == "published":
        raise HTTPException(status_code=400, detail="Published reports cannot be edited — create a new revision")
    if report.status == "submitted" and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="This report is submitted for review — an administrator can edit or return it, "
                   "or regenerate the draft (confirm_overwrite) to revise it.",
        )
    for field in REPORT_FIELDS:
        setattr(report, field, getattr(body, field))
    report.staff_notes = body.staff_notes
    await db.flush()
    return _serialize_report(report, include_staff=True)


@router.post("/reports/{report_id}/submit")
async def submit_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Instructor review step: hand the draft to the academy for approval."""
    await _require_staff(db, current_user)
    report = (await db.execute(select(MonthlyReport).where(MonthlyReport.id == report_id))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    instructor = await get_instructor_for_user(db, current_user)
    if instructor and report.instructor_id and report.instructor_id != instructor.id:
        raise HTTPException(status_code=403, detail="This report belongs to another instructor")
    if report.status == "published":
        raise HTTPException(status_code=400, detail="Published reports cannot be re-submitted")
    if report.status == "submitted":
        raise HTTPException(status_code=400, detail="This report is already submitted for review")
    report.status = "submitted"
    db.add(report)
    await db.flush()
    return _serialize_report(report, include_staff=True)


@router.post("/reports/{report_id}/publish")
async def publish_report(
    report_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin approval step: review and release the report to the student."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an administrator can approve and publish a report")
    await _require_staff(db, current_user)
    result = await db.execute(select(MonthlyReport).where(MonthlyReport.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    report.status = "published"
    report.published_at = dt.datetime.utcnow()
    await db.flush()

    student = await db.execute(select(Student).where(Student.id == report.student_id))
    student_row = student.scalar_one_or_none()
    if student_row:
        from app.services.notifications import notify_user

        await notify_user(
            db,
            user_id=student_row.user_id,
            type="report.published",
            title=f"Monthly report published — {report.report_month}",
            body="Your faculty report for this month is ready to view.",
            dedupe_key=f"report.published:{report.id}:{report.revision}",
            related_entity_type="monthly_report",
            related_entity_id=str(report.id),
        )
    return _serialize_report(report, include_staff=True)


# ==================================================================
# Syllabus
# ==================================================================
class SyllabusCreate(BaseModel):
    title: str
    board: str = "academy"
    programme_id: str
    grade: Optional[str] = None
    version: Optional[str] = None
    description: Optional[str] = None


class SyllabusItemCreate(BaseModel):
    title: str
    item_type: str = Field("topic", pattern="^(technical_work|repertoire|theory|milestone|topic)$")
    learning_objective: Optional[str] = None
    prerequisites: Optional[str] = None
    practice_instructions: Optional[str] = None
    faculty_notes: Optional[str] = None
    parent_item_id: Optional[UUID] = None
    sort_order: int = 0


class ProgressUpdate(BaseModel):
    status: str = Field(..., pattern="^(not_started|in_progress|completed)$")
    faculty_notes: Optional[str] = None
    evidence: Optional[str] = None


@router.get("/syllabi")
async def list_syllabi(
    programme_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Syllabi are student-specific: everyone except the admin sees only the
    syllabi explicitly assigned to their (or their children's / their
    students') learning plans."""
    query = select(Syllabus).where(Syllabus.is_active.is_(True))
    if programme_id:
        query = query.where(Syllabus.programme_id == programme_id)

    assignment_map = {}
    if current_user.role != UserRole.ADMIN:
        allowed = await _accessible_student_ids(db, current_user) or []
        if not allowed:
            return []
        assigns = (await db.execute(
            select(StudentSyllabusAssignment).where(
                StudentSyllabusAssignment.status == "active",
                StudentSyllabusAssignment.student_id.in_(allowed),
            ))).scalars().all()
        if not assigns:
            return []
        ids = {a.syllabus_id for a in assigns}
        query = query.where(Syllabus.id.in_(ids))
        for a in assigns:
            assignment_map.setdefault(a.syllabus_id, []).append(a)

    result = await db.execute(query.order_by(Syllabus.board.asc(), Syllabus.grade.asc()))
    out = []
    for s in result.scalars().all():
        items_result = await db.execute(
            select(SyllabusItem)
            .where(SyllabusItem.syllabus_id == s.id)
            .order_by(SyllabusItem.sort_order.asc())
        )
        items = list(items_result.scalars().all())
        out.append(
            {
                "id": str(s.id),
                "title": s.title,
                "board": s.board,
                "programme_id": s.programme_id,
                "grade": s.grade,
                "version": s.version,
                "description": s.description,
                "items": [
                    {
                        "id": str(i.id),
                        "title": i.title,
                        "item_type": i.item_type,
                        "learning_objective": i.learning_objective,
                        "practice_instructions": i.practice_instructions,
                        "parent_item_id": str(i.parent_item_id) if i.parent_item_id else None,
                        "sort_order": i.sort_order,
                    }
                    for i in items
                ],
                "assignments": [
                    {
                        "id": str(a.id),
                        "student_id": str(a.student_id),
                        "enrollment_id": str(a.enrollment_id),
                        "instructor_id": str(a.instructor_id) if a.instructor_id else None,
                        "status": a.status,
                    }
                    for a in assignment_map.get(s.id, [])
                ],
            }
        )
    return out


@router.post("/syllabi", status_code=status.HTTP_201_CREATED)
async def create_syllabus(
    body: SyllabusCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # admin-controlled syllabus catalogue
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an administrator can create a syllabus")
    syllabus = Syllabus(
        title=body.title,
        board=body.board,
        programme_id=body.programme_id,
        grade=body.grade,
        version=body.version,
        description=body.description,
        created_by=current_user.id,
    )
    db.add(syllabus)
    await db.flush()
    return {"id": str(syllabus.id), "title": syllabus.title}


@router.post("/syllabi/{syllabus_id}/items", status_code=status.HTTP_201_CREATED)
async def create_syllabus_item(
    syllabus_id: UUID,
    body: SyllabusItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an administrator can edit a syllabus")
    syllabus_result = await db.execute(select(Syllabus).where(Syllabus.id == syllabus_id))
    if not syllabus_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Syllabus not found")
    item = SyllabusItem(syllabus_id=syllabus_id, **body.model_dump())
    db.add(item)
    await db.flush()
    return {"id": str(item.id), "title": item.title}


class SyllabusAssignIn(BaseModel):
    student_id: UUID
    enrollment_id: UUID
    instructor_id: Optional[UUID] = None


class SyllabusAssignmentPatch(BaseModel):
    status: Optional[str] = None           # active | archived
    instructor_id: Optional[UUID] = None   # reassign teaching/review responsibility


class SyllabusPatch(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    grade: Optional[str] = None
    version: Optional[str] = None
    is_active: Optional[bool] = None


@router.post("/syllabi/{syllabus_id}/assign", status_code=status.HTTP_201_CREATED)
async def assign_syllabus_to_student(
    syllabus_id: UUID,
    body: SyllabusAssignIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin: put one syllabus on one student's learning plan.

    Two students on the same instrument can hold different syllabi; nothing
    here is ever shared outside the assigned student (and their linked
    parents / assigned instructor)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an administrator can assign a syllabus")

    syllabus = (await db.execute(select(Syllabus).where(Syllabus.id == syllabus_id))).scalar_one_or_none()
    if not syllabus:
        raise HTTPException(status_code=404, detail="Syllabus not found")
    enrollment = (await db.execute(
        select(Enrollment).where(Enrollment.id == body.enrollment_id))).scalar_one_or_none()
    if not enrollment or enrollment.student_id != body.student_id:
        raise HTTPException(status_code=400, detail="Enrolment does not belong to that student")

    existing = (await db.execute(
        select(StudentSyllabusAssignment).where(
            StudentSyllabusAssignment.syllabus_id == syllabus_id,
            StudentSyllabusAssignment.student_id == body.student_id,
            StudentSyllabusAssignment.enrollment_id == body.enrollment_id,
        ))).scalar_one_or_none()
    if existing:
        if existing.status == "archived":
            existing.status = "active"
            existing.assigned_by = current_user.id
            if body.instructor_id is not None:
                existing.instructor_id = body.instructor_id
            db.add(existing)
            await db.flush()
            return {"id": str(existing.id), "status": "active", "reactivated": True}
        raise HTTPException(status_code=409, detail="This syllabus is already assigned to that student/enrolment")

    assignment = StudentSyllabusAssignment(
        student_id=body.student_id,
        enrollment_id=body.enrollment_id,
        syllabus_id=syllabus_id,
        instructor_id=body.instructor_id or enrollment.instructor_id,
        status="active",
        assigned_by=current_user.id,
    )
    db.add(assignment)
    await db.flush()
    return {"id": str(assignment.id), "status": "active", "reactivated": False}


@router.patch("/syllabi/{syllabus_id}/assignments/{assignment_id}")
async def patch_syllabus_assignment(
    syllabus_id: UUID,
    assignment_id: UUID,
    body: SyllabusAssignmentPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin: archive/reopen a syllabus assignment or reassign its instructor."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an administrator can change a syllabus assignment")
    assignment = (await db.execute(
        select(StudentSyllabusAssignment).where(
            StudentSyllabusAssignment.id == assignment_id,
            StudentSyllabusAssignment.syllabus_id == syllabus_id,
        ))).scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    if body.status is not None:
        if body.status not in ("active", "archived"):
            raise HTTPException(status_code=400, detail="status must be active or archived")
        assignment.status = body.status
    if body.instructor_id is not None:
        assignment.instructor_id = body.instructor_id
    db.add(assignment)
    await db.flush()
    return {"id": str(assignment.id), "status": assignment.status,
            "instructor_id": str(assignment.instructor_id) if assignment.instructor_id else None}


@router.patch("/syllabi/{syllabus_id}")
async def patch_syllabus(
    syllabus_id: UUID,
    body: SyllabusPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin: edit catalogue fields or archive a syllabus (assignments keep
    their history; archival simply stops new use and hides it from portals)."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only an administrator can edit a syllabus")
    syllabus = (await db.execute(select(Syllabus).where(Syllabus.id == syllabus_id))).scalar_one_or_none()
    if not syllabus:
        raise HTTPException(status_code=404, detail="Syllabus not found")
    for field in ("title", "description", "grade", "version", "is_active"):
        value = getattr(body, field)
        if value is not None:
            setattr(syllabus, field, value)
    db.add(syllabus)
    await db.flush()
    return {"id": str(syllabus.id), "title": syllabus.title, "is_active": bool(syllabus.is_active)}


@router.get("/syllabus-progress")
async def syllabus_progress(
    student_id: UUID,
    syllabus_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await require_student_access(db, current_user, student_id)
    query = (
        select(StudentSyllabusProgress, SyllabusItem)
        .join(SyllabusItem, SyllabusItem.id == StudentSyllabusProgress.item_id)
        .where(StudentSyllabusProgress.student_id == student_id)
    )
    if syllabus_id:
        query = query.where(StudentSyllabusProgress.syllabus_id == syllabus_id)
    result = await db.execute(query)

    rows = result.all()
    completed = sum(1 for p, _ in rows if p.status == "completed")
    total = len(rows)
    return {
        "student_id": str(student_id),
        "completed": completed,
        "total": total,
        "percent": round((completed / total) * 100) if total else None,
        "items": [
            {
                "item_id": str(item.id),
                "syllabus_id": str(progress.syllabus_id),
                "title": item.title,
                "item_type": item.item_type,
                "status": progress.status,
                "faculty_notes": progress.faculty_notes,
                "date_introduced": progress.date_introduced.isoformat() if progress.date_introduced else None,
                "date_completed": progress.date_completed.isoformat() if progress.date_completed else None,
            }
            for progress, item in rows
        ],
    }


@router.post("/syllabus-progress/{item_id}", status_code=status.HTTP_201_CREATED)
async def upsert_syllabus_progress(
    item_id: UUID,
    body: ProgressUpdate,
    student_id: UUID,
    enrollment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Faculty records real progress updates (nothing is auto-completed)."""
    await _require_staff(db, current_user)
    await require_student_access(db, current_user, student_id)
    item_result = await db.execute(select(SyllabusItem).where(SyllabusItem.id == item_id))
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Syllabus item not found")

    existing = await db.execute(
        select(StudentSyllabusProgress).where(
            StudentSyllabusProgress.item_id == item_id,
            StudentSyllabusProgress.student_id == student_id,
        )
    )
    progress = existing.scalar_one_or_none()
    now = dt.datetime.utcnow()
    if not progress:
        progress = StudentSyllabusProgress(
            student_id=student_id,
            enrollment_id=enrollment_id,
            syllabus_id=item.syllabus_id,
            item_id=item.id,
        )
        db.add(progress)
        if body.status != "not_started":
            progress.date_introduced = now

    previous = progress.status
    progress.status = body.status
    progress.faculty_notes = body.faculty_notes
    progress.evidence = body.evidence
    progress.updated_by = current_user.id
    if body.status == "completed" and previous != "completed":
        progress.date_completed = now
    elif body.status != "completed":
        progress.date_completed = None
    await db.flush()

    await record_audit(
        db,
        action="syllabus.progress_updated",
        entity_type="student_syllabus_progress",
        entity_id=str(progress.id),
        actor_user_id=current_user.id,
        actor_role=current_user.role.value,
        before_data={"status": previous},
        after_data={"status": body.status},
    )
    return {"item_id": str(item_id), "status": progress.status}


# ==================================================================
# Exams & milestones
# ==================================================================
class ExamCreate(BaseModel):
    student_id: UUID
    enrollment_id: UUID
    board: str = "academy"
    instrument: str
    grade: Optional[str] = None
    pathway: Optional[str] = None
    exam_window_start: Optional[str] = None
    exam_window_end: Optional[str] = None
    submission_deadline: Optional[str] = None
    notes: Optional[str] = None


class ExamUpdate(BaseModel):
    application_status: Optional[str] = None
    payment_status: Optional[str] = None
    submission_status: Optional[str] = None
    submission_date: Optional[str] = None
    submission_reference: Optional[str] = None
    readiness: Optional[str] = None
    result: Optional[str] = None
    certificate_reference: Optional[str] = None
    exam_window_start: Optional[str] = None
    exam_window_end: Optional[str] = None
    submission_deadline: Optional[str] = None
    notes: Optional[str] = None


def _serialize_exam(e: Exam, items: List[ExamItem]) -> dict:
    return {
        "id": str(e.id),
        "student_id": str(e.student_id),
        "enrollment_id": str(e.enrollment_id),
        "board": e.board,
        "instrument": e.instrument,
        "grade": e.grade,
        "pathway": e.pathway,
        "application_status": e.application_status,
        "payment_status": e.payment_status,
        "exam_window_start": e.exam_window_start.isoformat() if e.exam_window_start else None,
        "exam_window_end": e.exam_window_end.isoformat() if e.exam_window_end else None,
        "submission_deadline": e.submission_deadline.isoformat() if e.submission_deadline else None,
        "submission_status": e.submission_status,
        "submission_date": e.submission_date.isoformat() if e.submission_date else None,
        "submission_reference": e.submission_reference,
        "readiness": e.readiness,
        "result": e.result,
        "certificate_reference": e.certificate_reference,
        "items": [
            {"id": str(i.id), "item_type": i.item_type, "title": i.title, "status": i.status}
            for i in items
        ],
    }


@router.get("/exams")
async def list_exams(
    student_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Exam)
    allowed = await _accessible_student_ids(db, current_user)
    if allowed is not None:
        if not allowed:
            return []
        query = query.where(Exam.student_id.in_(allowed))
    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(Exam.student_id == student_id)

    result = await db.execute(query.order_by(Exam.submission_deadline.asc().nullslast()))
    out = []
    for exam in result.scalars().all():
        items = await db.execute(
            select(ExamItem).where(ExamItem.exam_id == exam.id).order_by(ExamItem.sort_order.asc())
        )
        out.append(_serialize_exam(exam, list(items.scalars().all())))
    return out


@router.post("/exams", status_code=status.HTTP_201_CREATED)
async def create_exam(
    body: ExamCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    exam = Exam(
        student_id=body.student_id,
        enrollment_id=body.enrollment_id,
        board=body.board,
        instrument=body.instrument,
        grade=body.grade,
        pathway=body.pathway,
        exam_window_start=dt.date.fromisoformat(body.exam_window_start) if body.exam_window_start else None,
        exam_window_end=dt.date.fromisoformat(body.exam_window_end) if body.exam_window_end else None,
        submission_deadline=dt.date.fromisoformat(body.submission_deadline) if body.submission_deadline else None,
        notes=body.notes,
        created_by=current_user.id,
    )
    db.add(exam)
    await db.flush()
    return _serialize_exam(exam, [])


@router.patch("/exams/{exam_id}")
async def update_exam(
    exam_id: UUID,
    body: ExamUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    result = await db.execute(select(Exam).where(Exam.id == exam_id))
    exam = result.scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")

    data = body.model_dump(exclude_unset=True)
    for date_field in ("exam_window_start", "exam_window_end", "submission_deadline"):
        if date_field in data and data[date_field]:
            data[date_field] = dt.date.fromisoformat(data[date_field])
        elif date_field in data:
            data[date_field] = None
    if "submission_date" in data and data["submission_date"]:
        data["submission_date"] = dt.datetime.fromisoformat(data["submission_date"])

    for field, value in data.items():
        setattr(exam, field, value)
    await db.flush()
    items = await db.execute(select(ExamItem).where(ExamItem.exam_id == exam.id))
    return _serialize_exam(exam, list(items.scalars().all()))


class MilestoneCreate(BaseModel):
    student_id: UUID
    enrollment_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    milestone_type: str = "achievement"
    due_date: Optional[str] = None


@router.get("/milestones")
async def list_milestones(
    student_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Milestone)
    allowed = await _accessible_student_ids(db, current_user)
    if allowed is not None:
        if not allowed:
            return []
        query = query.where(Milestone.student_id.in_(allowed))
    if student_id:
        await require_student_access(db, current_user, student_id)
        query = query.where(Milestone.student_id == student_id)

    result = await db.execute(query.order_by(Milestone.due_date.asc().nullslast()))
    return [
        {
            "id": str(m.id),
            "student_id": str(m.student_id),
            "title": m.title,
            "description": m.description,
            "milestone_type": m.milestone_type,
            "due_date": m.due_date.isoformat() if m.due_date else None,
            "achieved_at": m.achieved_at.isoformat() if m.achieved_at else None,
            "status": m.status,
        }
        for m in result.scalars().all()
    ]


@router.post("/milestones", status_code=status.HTTP_201_CREATED)
async def create_milestone(
    body: MilestoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    milestone = Milestone(
        student_id=body.student_id,
        enrollment_id=body.enrollment_id,
        title=body.title,
        description=body.description,
        milestone_type=body.milestone_type,
        due_date=dt.date.fromisoformat(body.due_date) if body.due_date else None,
        created_by=current_user.id,
    )
    db.add(milestone)
    await db.flush()
    return {"id": str(milestone.id), "title": milestone.title}


# ==================================================================
# Recommended resources
# ==================================================================
class RecommendationCreate(BaseModel):
    resource_type: str = Field(..., pattern="^(book|instrument|accessory|stand_notebook|metronome_tuner|online_link)$")
    name: str = Field(..., min_length=2, max_length=200)
    author_or_brand: Optional[str] = None
    description: Optional[str] = None
    suitability: Optional[str] = None
    programme_id: Optional[str] = None
    image_url: Optional[str] = None
    external_url: Optional[str] = Field(None, max_length=500)
    faculty_note: Optional[str] = None
    sort_order: int = 0
    visibility_scope: Optional[str] = "all"
    target_student_ids: Optional[list] = None


class ResourcePatch(BaseModel):
    visibility_scope: Optional[str] = None
    target_student_ids: Optional[list] = None
    is_published: Optional[bool] = None
    is_active: Optional[bool] = None
    title: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    programme_id: Optional[str] = None


@router.get("/recommendations")
async def list_recommendations(
    resource_type: Optional[str] = None,
    programme_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    candidates = await _audience_student_ids_for_user(db, current_user)

    query = select(ResourceRecommendation).where(ResourceRecommendation.is_active.is_(True))
    if resource_type:
        query = query.where(ResourceRecommendation.resource_type == resource_type)
    if programme_id:
        query = query.where(
            (ResourceRecommendation.programme_id == programme_id)
            | (ResourceRecommendation.programme_id.is_(None))
        )
    result = await db.execute(query.order_by(ResourceRecommendation.sort_order.asc()))
    out = []
    for r in result.scalars().all():
        if candidates is not None:
            ok = await _audience_allows(
                db, kind="recommendation", resource_id=r.id,
                scope=r.visibility_scope or "all",
                programme_id=r.programme_id, level=None,
                student_ids=candidates,
            )
            if not ok:
                continue
        out.append(
            {
                "id": str(r.id),
                "resource_type": r.resource_type,
                "name": r.name,
                "author_or_brand": r.author_or_brand,
                "description": r.description,
                "suitability": r.suitability,
                "programme_id": r.programme_id,
                "visibility_scope": r.visibility_scope or "all",
                "image_url": r.image_url,
                "external_url": r.external_url,
                "faculty_note": r.faculty_note,
            }
        )
    return out


@router.post("/recommendations", status_code=status.HTTP_201_CREATED)
async def create_recommendation(
    body: RecommendationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    if body.external_url and not body.external_url.lower().startswith("https://"):
        raise HTTPException(status_code=400, detail="External links must use https://")
    scope = _parse_scope(body.visibility_scope)
    if scope == "programme" and not body.programme_id:
        raise HTTPException(status_code=400, detail="visibility_scope=programme needs a programme_id")
    payload = body.model_dump()
    payload.pop("target_student_ids", None)
    payload.pop("visibility_scope", None)
    row = ResourceRecommendation(**payload, visibility_scope=scope, created_by=current_user.id)
    db.add(row)
    await db.flush()
    targets = 0
    for sid in (body.target_student_ids or []):
        sid = UUID(str(sid))
        if not (await db.execute(select(Student).where(Student.id == sid))).scalar_one_or_none():
            raise HTTPException(status_code=400, detail=f"Unknown student {sid}")
        db.add(ResourceVisibilityTarget(
            resource_kind="recommendation", resource_id=row.id, student_id=sid,
            created_by=current_user.id))
        targets += 1
    await db.flush()
    return {"id": str(row.id), "name": row.name, "visibility_scope": scope,
            "target_students": targets}


@router.patch("/materials/{material_id}")
async def patch_material(
    material_id: UUID,
    body: ResourcePatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin/staff edit — including changing the visibility audience."""
    await _require_staff(db, current_user)
    m = (await db.execute(select(StudyMaterial).where(StudyMaterial.id == material_id))).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="Material not found")
    if body.visibility_scope is not None:
        m.visibility_scope = _parse_scope(body.visibility_scope)
    for field in ("title", "description", "level", "programme_id"):
        value = getattr(body, field)
        if value is not None:
            setattr(m, field, value)
    if body.is_published is not None:
        m.is_published = body.is_published
    db.add(m)
    if body.target_student_ids is not None:
        await db.execute(
            delete(ResourceVisibilityTarget).where(
                ResourceVisibilityTarget.resource_kind == "material",
                ResourceVisibilityTarget.resource_id == m.id,
            )
        )
        for sid in body.target_student_ids:
            sid = UUID(str(sid))
            db.add(ResourceVisibilityTarget(
                resource_kind="material", resource_id=m.id, student_id=sid,
                created_by=current_user.id))
    await db.flush()
    return {"id": str(m.id), "visibility_scope": m.visibility_scope or "all",
            "is_published": bool(m.is_published)}


@router.patch("/recommendations/{recommendation_id}")
async def patch_recommendation(
    recommendation_id: UUID,
    body: ResourcePatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _require_staff(db, current_user)
    r = (await db.execute(
        select(ResourceRecommendation).where(ResourceRecommendation.id == recommendation_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if body.visibility_scope is not None:
        r.visibility_scope = _parse_scope(body.visibility_scope)
    for field in ("name", "description", "programme_id"):
        value = getattr(body, field)
        if value is not None:
            setattr(r, field, value)
    if body.is_active is not None:
        r.is_active = body.is_active
    db.add(r)
    if body.target_student_ids is not None:
        await db.execute(
            delete(ResourceVisibilityTarget).where(
                ResourceVisibilityTarget.resource_kind == "recommendation",
                ResourceVisibilityTarget.resource_id == r.id,
            )
        )
        for sid in body.target_student_ids:
            sid = UUID(str(sid))
            db.add(ResourceVisibilityTarget(
                resource_kind="recommendation", resource_id=r.id, student_id=sid,
                created_by=current_user.id))
    await db.flush()
    return {"id": str(r.id), "visibility_scope": r.visibility_scope or "all",
            "is_active": bool(r.is_active)}
