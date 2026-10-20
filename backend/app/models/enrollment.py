import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class EnrollmentStatus(str):
    ACTIVE = "active"
    INACTIVE = "inactive"
    COMPLETED = "completed"
    SUSPENDED = "suspended"
    TRANSFERRED = "transferred"


class Enrollment(Base):
    __tablename__ = "enrollments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Student & Programme
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    programme_id = Column(String(50), nullable=False)  # piano, acoustic_guitar, etc.
    programme_name = Column(String(100), nullable=False)  # Piano, Acoustic Guitar, etc.
    
    # Instructor assignment
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id"), nullable=True)
    
    # Fee plan
    fee_plan = Column(String(20))  # 4_classes, 8_classes
    fee_amount = Column(Numeric(10, 2))  # 4500.00 or 8000.00
    
    # Status
    status = Column(String(20), default=EnrollmentStatus.ACTIVE, nullable=False)
    
    # Dates
    start_date = Column(Date)
    end_date = Column(Date)
    
    # Notes
    notes = Column(Text)
    
    # Relationships
    student = relationship("Student", backref="enrollments")
    instructor = relationship("Instructor", backref="enrollments")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
