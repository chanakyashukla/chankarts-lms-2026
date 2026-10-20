import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Syllabus(Base):
    """
    A learning pathway: board syllabus (Trinity / Rockschool / ...) or an
    academy-owned pathway (e.g. Indian Bansuri). Instruments are not forced
    onto a single board.
    """

    __tablename__ = "syllabi"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    title = Column(String(200), nullable=False)
    board = Column(String(80), nullable=False, default="academy")  # academy, trinity, rockschool, ...
    programme_id = Column(String(50), nullable=False, index=True)  # piano, indian_bansuri, ...
    grade = Column(String(40))                                     # Grade 1, Intermediate, ...
    version = Column(String(40))
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SyllabusItem(Base):
    """A topic/skill node in a syllabus (supports nesting for groups)."""

    __tablename__ = "syllabus_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    syllabus_id = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_item_id = Column(UUID(as_uuid=True), ForeignKey("syllabus_items.id", ondelete="CASCADE"), nullable=True, index=True)

    title = Column(String(200), nullable=False)
    item_type = Column(String(30), default="topic")  # technical_work, repertoire, theory, milestone, topic
    learning_objective = Column(Text)
    prerequisites = Column(Text)
    practice_instructions = Column(Text)
    faculty_notes = Column(Text)
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class StudentSyllabusProgress(Base):
    """
    Per-student progress for one syllabus item. Progress reflects actual
    faculty updates only — nothing is auto-completed.
    """

    __tablename__ = "student_syllabus_progress"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    syllabus_id = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False, index=True)
    item_id = Column(UUID(as_uuid=True), ForeignKey("syllabus_items.id", ondelete="CASCADE"), nullable=False, index=True)

    status = Column(String(20), default="not_started", nullable=False)  # not_started, in_progress, completed
    faculty_notes = Column(Text)
    evidence = Column(Text)
    date_introduced = Column(DateTime)
    date_completed = Column(DateTime)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "item_id", name="uq_progress_student_item"),
    )


class StudentSyllabusAssignment(Base):
    """An explicit admin decision that one syllabus belongs to one student's
    learning plan. A syllabus is never implicitly shared with other students:
    it becomes visible only through an active assignment (or, for legacy
    records, an assignment backfilled from existing progress rows)."""

    __tablename__ = "student_syllabus_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    syllabus_id = Column(UUID(as_uuid=True), ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False, index=True)

    # teaching/review responsibility; defaults to the enrolment's instructor
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id", ondelete="SET NULL"), nullable=True)

    status = Column(String(20), default="active", nullable=False)   # active, archived
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("student_id", "syllabus_id", "enrollment_id", name="uq_syllabus_assignment"),
    )
