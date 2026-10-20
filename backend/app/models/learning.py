import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Integer, Boolean, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Assignment(Base):
    """Faculty/admin assigned work for a student, enrollment, group or selection."""

    __tablename__ = "assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    title = Column(String(200), nullable=False)
    instructions = Column(Text)
    practice_notes = Column(Text)

    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    assigned_date = Column(Date, nullable=False)
    due_date = Column(Date, index=True)
    priority = Column(String(12), default="normal")   # low, normal, high
    status = Column(String(20), default="assigned", nullable=False)  # assigned, submitted, reviewed, revision_requested

    allow_audio = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AssignmentFile(Base):
    """Attachment owned by faculty (brief) or student (homework)."""

    __tablename__ = "assignment_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    submission_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    owner_role = Column(String(20), nullable=False)   # faculty | student

    filename = Column(String(255), nullable=False)
    stored_name = Column(String(80), nullable=False, unique=True)  # non-guessable storage name
    content_type = Column(String(120), nullable=False)             # verified server-side, not from extension
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class Submission(Base):
    """One student submission attempt with faculty feedback and revision history."""

    __tablename__ = "submissions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)

    attempt_number = Column(Integer, default=1, nullable=False)
    notes = Column(Text)
    status = Column(String(20), default="submitted", nullable=False)  # submitted, reviewed, revision_requested
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    feedback = Column(Text)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class StudyMaterial(Base):
    """Downloadable learning material with visibility scoped to course/level."""

    __tablename__ = "study_materials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    title = Column(String(200), nullable=False)
    description = Column(Text)
    category = Column(String(40), nullable=False, index=True)  # technique, repertoire, theory, ear_training, rhythm, exam_preparation, practice
    programme_id = Column(String(50), index=True)              # course applicability (null = all)
    level = Column(String(40))                                 # beginner, intermediate, advanced, grade_1 ...

    material_type = Column(String(20), nullable=False, default="file")  # file, link
    stored_name = Column(String(80), unique=True)                         # for files
    filename = Column(String(255))
    content_type = Column(String(120))
    size_bytes = Column(Integer)
    link_url = Column(String(500))

    version = Column(String(20), default="1.0")
    is_published = Column(Boolean, default=True, nullable=False)

    # audience: all | students (explicit targets) | programme | level
    # combined conditions (e.g. programme + level) are always ANDed
    visibility_scope = Column(String(20), default="all")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class MaterialAssignment(Base):
    """Targeted assignment of a material to a student or enrollment."""

    __tablename__ = "material_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    material_id = Column(UUID(as_uuid=True), ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=True, index=True)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ResourceRecommendation(Base):
    """Faculty-managed recommendation (books, instruments, accessories, links). Not a store."""

    __tablename__ = "resource_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    resource_type = Column(String(30), nullable=False, index=True)  # book, instrument, accessory, stand_notebook, metronome_tuner, online_link
    name = Column(String(200), nullable=False)
    author_or_brand = Column(String(200))
    description = Column(Text)
    suitability = Column(String(120))     # e.g. "Beginner to Intermediate"
    programme_id = Column(String(50), index=True)
    image_url = Column(String(500))
    external_url = Column(String(500))    # legitimate outbound link only
    faculty_note = Column(Text)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)

    # audience: all | students (explicit targets) | programme | level
    visibility_scope = Column(String(20), default="all")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class ResourceVisibilityTarget(Base):
    """Explicit per-student targeting for study materials and recommendations.

    A row here always grants that student access (union with the scope base).
    Student-specific resources rely on these rows and are never implicitly
    shared with the whole academy."""

    __tablename__ = "resource_visibility_targets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    resource_kind = Column(String(20), nullable=False, index=True)  # material | recommendation
    resource_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("resource_kind", "resource_id", "student_id", name="uq_resource_target"),
    )
