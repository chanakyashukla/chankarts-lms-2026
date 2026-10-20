import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Notification(Base):
    """User-facing notification with de-duplication support."""

    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = Column(String(60), nullable=False)   # registration.received, payment.confirmed, class.reminder, ...
    title = Column(String(200), nullable=False)
    body = Column(Text)
    channel = Column(String(20), default="in_app")  # in_app, email
    status = Column(String(20), default="pending")  # pending, sent, failed, suppressed

    # Idempotency: unique key prevents duplicates when jobs/webhooks retry
    dedupe_key = Column(String(160), unique=True, index=True)

    related_entity_type = Column(String(60))
    related_entity_id = Column(String(64))

    sent_at = Column(DateTime)
    read_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
