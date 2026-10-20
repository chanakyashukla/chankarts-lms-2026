import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class AuditEvent(Base):
    """Immutable audit trail for administrative, billing and permission changes."""

    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_role = Column(String(20))

    action = Column(String(80), nullable=False)          # e.g. registration.approved, payment.allocated
    entity_type = Column(String(60), nullable=False)     # e.g. registration_request, invoice
    entity_id = Column(String(64))                       # string form; entity may be uuid or business id

    summary = Column(Text)
    before_data = Column(JSON)
    after_data = Column(JSON)

    ip_address = Column(String(64))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
