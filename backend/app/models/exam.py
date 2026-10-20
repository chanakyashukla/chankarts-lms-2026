import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Exam(Base):
    """
    Examination record (board exam or internal academy assessment).

    A due date is never treated as proof of submission: submission status,
    date and reference are stored independently from the deadline.
    """

    __tablename__ = "exams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    syllabus_id = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="SET NULL"), nullable=True)

    board = Column(String(80), nullable=False, default="academy")  # academy, trinity, rockschool, ...
    instrument = Column(String(100), nullable=False)
    grade = Column(String(40))
    pathway = Column(String(80))

    application_status = Column(String(24), default="not_started", nullable=False)  # not_started, preparing, applied, confirmed
    payment_status = Column(String(24), default="not_applicable")                    # not_applicable, pending, paid

    exam_window_start = Column(Date)
    exam_window_end = Column(Date)
    submission_deadline = Column(Date, index=True)

    # Actual submission state — independent of the deadline
    submission_status = Column(String(24), default="not_submitted", nullable=False)  # not_submitted, preparing, submitted
    submission_date = Column(DateTime)
    submission_reference = Column(String(120))

    readiness = Column(String(24), default="not_assessed")  # not_assessed, developing, ready, exam_ready
    result = Column(String(40))                             # pending, pass, merit, distinction ...
    certificate_reference = Column(String(120))
    certificate_issued_at = Column(DateTime)

    notes = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ExamItem(Base):
    """Required repertoire / technical / theory item attached to an exam."""

    __tablename__ = "exam_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)

    item_type = Column(String(30), nullable=False, default="repertoire")  # repertoire, technical, theory, sight_reading, aural
    title = Column(String(200), nullable=False)
    details = Column(Text)
    status = Column(String(20), default="pending", nullable=False)        # pending, in_progress, ready
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Milestone(Base):
    """Non-exam achievement / progress milestone (academy pathways, workshops...)."""

    __tablename__ = "milestones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=True, index=True)

    title = Column(String(200), nullable=False)
    description = Column(Text)
    milestone_type = Column(String(40), default="achievement")  # achievement, workshop, performance, assessment
    due_date = Column(Date, index=True)
    achieved_at = Column(DateTime)
    status = Column(String(20), default="upcoming", nullable=False)  # upcoming, achieved

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
