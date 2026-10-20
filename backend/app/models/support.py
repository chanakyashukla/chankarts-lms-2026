import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class SupportRequest(Base):
    """A message from a student, parent or instructor to academy administration.

    Conversations are private to their sender (and the admin inbox) — there is
    no cross-user visibility. No email/SMS delivery is claimed anywhere: the
    conversation lives in the portal and replies raise in-portal notifications.
    """

    __tablename__ = "support_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    sender_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_role = Column(String(20), nullable=False)   # student | parent | instructor | admin

    subject = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)

    # optional authorised context — only records the sender may access
    related_student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    related_enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True)
    related_session_id = Column(UUID(as_uuid=True), ForeignKey("class_sessions.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(20), default="open", nullable=False, index=True)  # open, replied, resolved
    resolved_at = Column(DateTime)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SupportReply(Base):
    """One message in a support conversation (either direction)."""

    __tablename__ = "support_replies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("support_requests.id", ondelete="CASCADE"), nullable=False, index=True)

    author_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_role = Column(String(20), nullable=False)   # student | parent | instructor | admin

    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class SupportAttachment(Base):
    """Optional file attached to a support message (type/size validated server-side)."""

    __tablename__ = "support_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("support_requests.id", ondelete="CASCADE"), nullable=False, index=True)
    reply_id = Column(UUID(as_uuid=True), ForeignKey("support_replies.id", ondelete="CASCADE"), nullable=True, index=True)

    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    filename = Column(String(255), nullable=False)
    stored_name = Column(String(80), nullable=False, unique=True)
    content_type = Column(String(120), nullable=False)
    size_bytes = Column(Integer)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
