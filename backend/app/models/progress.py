import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Progress(Base):
    __tablename__ = "progress"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Links
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id"), nullable=False)
    
    # Progress details
    month = Column(String(7), nullable=False)  # MM-YYYY
    topics_covered = Column(Text)
    progress_summary = Column(Text)
    practice_notes = Column(Text)
    instructor_remarks = Column(Text)
    next_month_focus = Column(Text)
    
    # Relationships
    enrollment = relationship("Enrollment", backref="progress_records")
    student = relationship("Student", backref="progress_records")
    instructor = relationship("Instructor", backref="progress_records")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
