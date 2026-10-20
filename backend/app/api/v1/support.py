"""
Two-way communication with academy administration.

Students, parents and instructors contact the admin team from the portal;
administrators answer from a centralised inbox and resolve conversations.
Privacy: senders see only their own threads; only the admin inbox sees all.
No email, SMS or WhatsApp delivery is performed or claimed — replies create
in-app notifications through the existing notification service.
"""
from datetime import datetime
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
from app.models.enrollment import Enrollment
from app.models.student import Student
from app.models.support import SupportAttachment, SupportReply, SupportRequest
from app.models.user import User
from app.services.access import get_instructor_for_user, require_student_access
from app.services.files import BASE_HOMEWORK_TYPES, safe_filename, save_upload
from app.services.notifications import notify_user

portal_router = APIRouter()
admin_router = APIRouter()


class SupportCreate(BaseModel):
    subject: str = Field(..., min_length=3, max_length=200)
    message: str = Field(..., min_length=5)
    related_student_id: Optional[UUID] = None
    related_enrollment_id: Optional[UUID] = None
    related_session_id: Optional[UUID] = None


class SupportReplyIn(BaseModel):
    body: str = Field(..., min_length=1)


class SupportStatusIn(BaseModel):
    status: str = Field(..., pattern="^(open|replied|resolved)$")


def _serialize_request(req: SupportRequest, reply_count: int = 0) -> dict:
    return {
        "id": str(req.id),
        "subject": req.subject,
        "message": req.message,
        "status": req.status,
        "sender_role": req.sender_role,
        "related_student_id": str(req.related_student_id) if req.related_student_id else None,
        "related_enrollment_id": str(req.related_enrollment_id) if req.related_enrollment_id else None,
        "related_session_id": str(req.related_session_id) if req.related_session_id else None,
        "reply_count": reply_count,
        "resolved_at": req.resolved_at.isoformat() if req.resolved_at else None,
        "created_at": req.created_at.isoformat() if req.created_at else None,
        "updated_at": req.updated_at.isoformat() if req.updated_at else None,
    }


def _serialize_reply(r: SupportReply) -> dict:
    return {
        "id": str(r.id),
        "author_role": r.author_role,
        "body": r.body,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


async def _load_own_request(db: AsyncSession, user: User, request_id: UUID) -> SupportRequest:
    req = (await db.execute(select(SupportRequest).where(SupportRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if req.sender_user_id != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="You can only view your own conversations")
    return req


# ==================================================================
# Portal side — send and follow your own conversations
# ==================================================================
@portal_router.post("/support", status_code=status.HTTP_201_CREATED)
async def create_support_request(
    body: SupportCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Contact academy administration. Related records are optional and must
    be records the sender is already authorised to access."""
    if body.related_student_id:
        await require_student_access(db, current_user, body.related_student_id)
    if body.related_enrollment_id:
        enrollment = (await db.execute(
            select(Enrollment).where(Enrollment.id == body.related_enrollment_id))).scalar_one_or_none()
        if not enrollment:
            raise HTTPException(status_code=404, detail="Enrolment not found")
        await require_student_access(db, current_user, enrollment.student_id)

    req = SupportRequest(
        sender_user_id=current_user.id,
        sender_role=current_user.role.value,
        subject=body.subject.strip(),
        message=body.message.strip(),
        related_student_id=body.related_student_id,
        related_enrollment_id=body.related_enrollment_id,
        related_session_id=body.related_session_id,
        status="open",
    )
    db.add(req)
    await db.flush()
    return _serialize_request(req)


@portal_router.get("/support")
async def list_my_support_requests(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(SupportRequest)
        .where(SupportRequest.sender_user_id == current_user.id)
        .order_by(SupportRequest.updated_at.desc())
    )).scalars().all()
    out = []
    for req in rows:
        count = (await db.execute(
            select(SupportReply.id).where(SupportReply.request_id == req.id)
        )).scalars().all()
        out.append(_serialize_request(req, reply_count=len(count)))
    return out


@portal_router.get("/support/{request_id}")
async def get_my_support_request(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = await _load_own_request(db, current_user, request_id)
    replies = (await db.execute(
        select(SupportReply).where(SupportReply.request_id == req.id).order_by(SupportReply.created_at.asc())
    )).scalars().all()
    files = (await db.execute(
        select(SupportAttachment).where(SupportAttachment.request_id == req.id)
    )).scalars().all()
    payload = _serialize_request(req, reply_count=len(replies))
    payload["replies"] = [_serialize_reply(r) for r in replies]
    payload["attachments"] = [
        {"id": str(f.id), "filename": f.filename, "content_type": f.content_type,
         "stored_name": f.stored_name,
         "reply_id": str(f.reply_id) if f.reply_id else None}
        for f in files
    ]
    return payload


@portal_router.post("/support/{request_id}/reply", status_code=status.HTTP_201_CREATED)
async def reply_to_own_request(
    request_id: UUID,
    body: SupportReplyIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Follow up on your own conversation. Once resolved by the academy,
    contact administration again with a new request instead."""
    req = await _load_own_request(db, current_user, request_id)
    if req.sender_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the sender can add to this conversation")
    if req.status == "resolved":
        raise HTTPException(status_code=400, detail="This conversation is resolved — please submit a new request")
    reply = SupportReply(
        request_id=req.id,
        author_user_id=current_user.id,
        author_role=current_user.role.value,
        body=body.body.strip(),
    )
    db.add(reply)
    req.status = "open"
    db.add(req)
    await db.flush()
    return _serialize_reply(reply)


@portal_router.post("/support/{request_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_support_attachment(
    request_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Optional attachment — server-side file type and size validation."""
    req = await _load_own_request(db, current_user, request_id)
    if req.sender_user_id != current_user.id and current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only the sender can attach files")
    stored_name, content_type, size, _ = await save_upload(
        file, subdir="support", allowed_types=BASE_HOMEWORK_TYPES
    )
    att = SupportAttachment(
        request_id=req.id,
        uploaded_by=current_user.id,
        filename=safe_filename(file.filename),
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=size,
    )
    db.add(att)
    await db.flush()
    return {"id": str(att.id), "filename": att.filename, "content_type": content_type}


@portal_router.get("/support/files/{stored_name}")
async def download_support_file(
    stored_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    att = (await db.execute(
        select(SupportAttachment).where(SupportAttachment.stored_name == stored_name))).scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="File not found")
    req = await _load_own_request(db, current_user, att.request_id)
    from app.services.files import resolve_stored_file
    path = resolve_stored_file("support", stored_name)
    if path is None:
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(path, media_type=att.content_type, filename=att.filename)


# ==================================================================
# Admin side — centralised inbox
# ==================================================================
def _sender_name(db_user: Optional[User], student: Optional[Student]) -> str:
    if student:
        return student.full_name
    if db_user:
        return db_user.username
    return "Unknown"


@admin_router.get("/support")
async def admin_list_support(
    status_filter: Optional[str] = None,
    role_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    query = select(SupportRequest).order_by(SupportRequest.updated_at.desc())
    if status_filter:
        query = query.where(SupportRequest.status == status_filter)
    if role_filter:
        query = query.where(SupportRequest.sender_role == role_filter)
    rows = (await db.execute(query)).scalars().all()

    user_ids = {r.sender_user_id for r in rows if r.sender_user_id}
    student_ids = {r.related_student_id for r in rows if r.related_student_id}
    users, students = {}, {}
    if user_ids:
        for u in (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all():
            users[u.id] = u
    if student_ids:
        for st in (await db.execute(select(Student).where(Student.id.in_(student_ids)))).scalars().all():
            students[st.id] = st

    out = []
    for req in rows:
        reply_count = len((await db.execute(
            select(SupportReply.id).where(SupportReply.request_id == req.id))).scalars().all())
        payload = _serialize_request(req, reply_count=reply_count)
        payload["sender_name"] = _sender_name(users.get(req.sender_user_id), None)
        if req.related_student_id:
            st = students.get(req.related_student_id)
            payload["related_student_name"] = st.full_name if st else None
        out.append(payload)
    return out


@admin_router.get("/support/{request_id}")
async def admin_get_support(
    request_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    req = (await db.execute(select(SupportRequest).where(SupportRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Conversation not found")
    replies = (await db.execute(
        select(SupportReply).where(SupportReply.request_id == req.id).order_by(SupportReply.created_at.asc())
    )).scalars().all()
    files = (await db.execute(
        select(SupportAttachment).where(SupportAttachment.request_id == req.id)
    )).scalars().all()
    sender = (await db.execute(select(User).where(User.id == req.sender_user_id))).scalar_one_or_none()
    student = None
    if req.related_student_id:
        student = (await db.execute(
            select(Student).where(Student.id == req.related_student_id))).scalar_one_or_none()
    payload = _serialize_request(req, reply_count=len(replies))
    payload["sender_name"] = _sender_name(sender, student if req.sender_role == "student" else None)
    payload["sender_username"] = sender.username if sender else None
    if student:
        payload["related_student_name"] = student.full_name
        payload["related_student_cma"] = student.cma_registration_id
    payload["replies"] = [_serialize_reply(r) for r in replies]
    payload["attachments"] = [
        {"id": str(f.id), "filename": f.filename, "content_type": f.content_type,
         "reply_id": str(f.reply_id) if f.reply_id else None}
        for f in files
    ]
    return payload


@admin_router.post("/support/{request_id}/reply", status_code=status.HTTP_201_CREATED)
async def admin_reply_support(
    request_id: UUID,
    body: SupportReplyIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    req = (await db.execute(select(SupportRequest).where(SupportRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Conversation not found")
    reply = SupportReply(
        request_id=req.id,
        author_user_id=current_user.id,
        author_role="admin",
        body=body.body.strip(),
    )
    db.add(reply)
    req.status = "replied"
    db.add(req)
    await db.flush()

    await notify_user(
        db,
        user_id=req.sender_user_id,
        type="support.reply",
        title=f"Academy replied: {req.subject[:60]}",
        body="You have a response from academy administration in Help & Support.",
        dedupe_key=f"support.reply:{reply.id}",
        related_entity_type="support_request",
        related_entity_id=str(req.id),
    )
    return _serialize_reply(reply)


@admin_router.post("/support/{request_id}/status")
async def admin_set_support_status(
    request_id: UUID,
    body: SupportStatusIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    req = (await db.execute(select(SupportRequest).where(SupportRequest.id == request_id))).scalar_one_or_none()
    if not req:
        raise HTTPException(status_code=404, detail="Conversation not found")
    req.status = body.status
    if body.status == "resolved":
        req.resolved_at = datetime.utcnow()
        req.resolved_by = current_user.id
        await notify_user(
            db,
            user_id=req.sender_user_id,
            type="support.resolved",
            title=f"Resolved: {req.subject[:60]}",
            body="Academy administration marked your request as resolved.",
            dedupe_key=f"support.resolved:{req.id}",
            related_entity_type="support_request",
            related_entity_id=str(req.id),
        )
    else:
        req.resolved_at = None
        req.resolved_by = None
    db.add(req)
    await db.flush()
    return _serialize_request(req)


@admin_router.get("/support/files/{stored_name}")
async def admin_download_support_file(
    stored_name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN])),
):
    att = (await db.execute(
        select(SupportAttachment).where(SupportAttachment.stored_name == stored_name))).scalar_one_or_none()
    if not att:
        raise HTTPException(status_code=404, detail="File not found")
    from app.services.files import resolve_stored_file
    path = resolve_stored_file("support", stored_name)
    if path is None:
        raise HTTPException(status_code=404, detail="File missing")
    return FileResponse(path, media_type=att.content_type, filename=att.filename)
