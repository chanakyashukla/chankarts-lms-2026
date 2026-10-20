import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class RemarkVisibility(str):
    """Explicit visibility for additional remarks — never inferred."""
    STAFF_ONLY = "staff_only"          # internal academy record, never leaves staff
    STUDENT_VISIBLE = "student_visible"  # shown to the student in their portal
    PARENT_VISIBLE = "parent_visible"    # shown to linked guardians in their portal


class StudentRemark(Base):
    """
    Additional remark attached to a student (and optionally a specific enrollment),
    with an explicit visibility field. There is no default visibility: the author
    must choose. Staff-only remarks are never serialized to student/parent
    API responses, reports, downloads or any other channel.
    """

    __tablename__ = "student_remarks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True, index=True)

    author_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    author_role = Column(String(20))

    visibility = Column(String(20), nullable=False)  # staff_only | student_visible | parent_visible
    body = Column(Text, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
