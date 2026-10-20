import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, Time, ForeignKey, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class SessionStatus:
    """Calendar status model — there is deliberately NO 'absent' status.

    Red (rescheduling_required) means the agreed time must be moved; it never
    means the student was absent or that a class was forfeited.
    """

    SCHEDULED = "scheduled"                  # yellow
    COMPLETED = "completed"                  # green
    RESCHEDULED = "rescheduled"              # moved to a confirmed new date/time
    RESCHEDULING_REQUIRED = "rescheduling_required"  # red
    CANCELLED = "cancelled"                  # neutral

    ALL = (SCHEDULED, COMPLETED, RESCHEDULING_REQUIRED, CANCELLED)


class ClassSession(Base):
    """
    One teaching session between an instructor and a student for an enrollment.

    The originally scheduled record is never overwritten when a class is
    rescheduled: a replacement session is created with `replaces_session_id`
    pointing at the original, keeping the audit history intact.
    """

    __tablename__ = "class_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id", ondelete="CASCADE"), nullable=True, index=True)  # nullable: instructor not yet assigned

    # Scheduled (agreed) slot
    scheduled_date = Column(Date, nullable=False, index=True)
    scheduled_start = Column(Time, nullable=False)
    scheduled_end = Column(Time, nullable=False)
    timezone = Column(String(40), default="Asia/Kolkata", nullable=False)
    duration_minutes = Column(Integer, nullable=False, default=60)

    # Actual delivery (only for completed sessions; may differ from the agreed slot)
    actual_date = Column(Date)
    actual_start = Column(Time)
    actual_end = Column(Time)
    actual_duration_minutes = Column(Integer)

    # Lifecycle
    status = Column(String(30), default=SessionStatus.SCHEDULED, nullable=False, index=True)

    # Teaching record
    topics_covered = Column(Text)
    faculty_remarks = Column(Text)

    # Rescheduling
    # Student/instructor proposed alternative slot (reschedule request)
    preferred_date = Column(Date, nullable=True)
    preferred_start = Column(Time, nullable=True)
    preferred_end = Column(Time, nullable=True)
    reschedule_reason = Column(Text)
    practice_recommendations = Column(Text, nullable=True)   # practice notes for the student
    replaces_session_id = Column(UUID(as_uuid=True), ForeignKey("class_sessions.id", ondelete="SET NULL"), nullable=True, index=True)

    # Exceptions (e.g. legacy 30-minute contractual sessions) stay explicit
    is_duration_exception = Column(Boolean, default=False, nullable=False)
    exception_note = Column(Text)

    # Delivery accounting: count each delivered class exactly once per enrollment
    counts_toward_package = Column(Boolean, default=True, nullable=False)
    billing_month = Column(String(7))  # YYYY-MM of the delivered class

    is_online = Column(Boolean, default=False)
    location = Column(String(200))
    meeting_link = Column(String(500))

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    student = relationship("Student", backref="class_sessions")
    instructor = relationship("Instructor", backref="class_sessions")
    enrollment = relationship("Enrollment", backref="class_sessions")
    replaces = relationship("ClassSession", remote_side=[id], backref="replacements")


class SessionStatusHistory(Base):
    """Append-only history of session status transitions."""

    __tablename__ = "session_status_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False, index=True)

    from_status = Column(String(30))
    to_status = Column(String(30), nullable=False)
    reason = Column(Text)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
