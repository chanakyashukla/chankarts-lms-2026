import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class MonthlyReport(Base):
    """
    One structured faculty report per student/enrollment/billing month, with
    revision history. Students/parents see only published content; internal
    staff notes are never exposed to them.
    """

    __tablename__ = "monthly_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id", ondelete="SET NULL"), nullable=True)

    report_month = Column(String(7), nullable=False, index=True)  # YYYY-MM

    revision = Column(Integer, default=1, nullable=False)
    previous_revision_id = Column(UUID(as_uuid=True), ForeignKey("monthly_reports.id", ondelete="SET NULL"), nullable=True)

    progress_summary = Column(Text)
    topics_covered = Column(Text)
    skills_demonstrated = Column(Text)
    strengths = Column(Text)
    areas_for_improvement = Column(Text)
    practice_recommendations = Column(Text)
    assignment_status = Column(Text)
    syllabus_progress = Column(Text)
    exam_preparation = Column(Text)
    next_month_focus = Column(Text)
    faculty_remarks = Column(Text)

    staff_notes = Column(Text)  # internal only — never sent to student/parent

    status = Column(String(20), default="draft", nullable=False, index=True)  # draft, published
    published_at = Column(DateTime)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("enrollment_id", "report_month", "revision", name="uq_report_enrollment_month_revision"),
    )
