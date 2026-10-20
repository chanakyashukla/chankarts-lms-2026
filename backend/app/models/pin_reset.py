import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class PinResetRequestStatus(str):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PinResetRequest(Base):
    """Student-initiated "Forgot PIN" request (admin-managed recovery only).

    Deliberately stores only what the student typed — never a PIN, never a
    password hash. Existence of an account is never revealed to the submitter
    (the public endpoint returns an identical generic response either way).
    """

    __tablename__ = "pin_reset_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # PINREQ-YYYY-#### — sequential, unique
    request_id = Column(String(20), unique=True, index=True, nullable=False)

    # What the student submitted (login id they believe is theirs + how to reach them)
    username_submitted = Column(String(100), nullable=False, index=True)
    contact = Column(String(255), nullable=False)
    details = Column(Text)

    status = Column(String(20), default=PinResetRequestStatus.PENDING, nullable=False, index=True)

    # Resolution (admin only) — the issued PIN is NEVER stored here, only in
    # users.hashed_password after generation.
    reviewed_by = Column(UUID(as_uuid=True))
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    resolved_user_id = Column(UUID(as_uuid=True))  # account actually reset (when found)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
