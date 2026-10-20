import uuid
from datetime import datetime, date
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class AttendanceStatus(str):
    PRESENT = "present"
    ABSENT = "absent"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"


class Attendance(Base):
    __tablename__ = "attendance"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Links
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id"), nullable=False)
    
    # Attendance details
    class_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False)  # present, absent, cancelled, rescheduled
    
    # Notes
    notes = Column(Text)
    
    # Relationships
    enrollment = relationship("Enrollment", backref="attendance_records")
    student = relationship("Student", backref="attendance_records")
    instructor = relationship("Instructor", backref="attendance_records")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
