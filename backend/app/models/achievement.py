import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Achievement(Base):
    """A verified student achievement earned through the academy.

    Exam results, distinctions, certificates, recitals and similar
    accomplishments. Records are visible only to the student, their linked
    parents, their assigned instructors and administrators — there is no
    public showcase. Nothing is published until the academy verifies it.
    Historical achievements (earlier cohorts) can be entered when reliable
    records exist; results are never invented.
    """

    __tablename__ = "achievements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)

    title = Column(String(200), nullable=False)
    category = Column(String(40), nullable=False, default="award")  # exam, recital, competition, certification, award, milestone
    awarding_body = Column(String(120))     # Trinity, Rockschool, academy, ...
    programme_id = Column(String(50))       # instrument/course
    grade_level = Column(String(40))        # Grade 1, Intermediate, ...
    result = Column(String(80))             # Distinction, Merit, Pass, Winner, ...
    achieved_on = Column(Date)
    description = Column(Text)

    # optional certificate (image/PDF), validated server-side
    cert_stored_name = Column(String(80))
    cert_filename = Column(String(255))
    cert_content_type = Column(String(120))

    is_verified = Column(Boolean, default=False, nullable=False)   # only shown once verified
    is_archived = Column(Boolean, default=False, nullable=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
