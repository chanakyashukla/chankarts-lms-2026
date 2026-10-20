import uuid
from datetime import datetime, time
from sqlalchemy import Column, String, DateTime, Date, Time, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class ClassSchedule(Base):
    __tablename__ = "class_schedules"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Links
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id"), nullable=True)  # nullable: instructor not yet assigned
    
    # Schedule details
    day_of_week = Column(String(10), nullable=False)  # monday, tuesday, etc.
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    frequency = Column(String(20), default="weekly")  # weekly, biweekly
    
    # Location
    is_online = Column(Boolean, default=False)
    location = Column(String(200))
    meeting_link = Column(String(500))
    
    # Status
    is_active = Column(Boolean, default=True)
    start_date = Column(Date)
    end_date = Column(Date)
    
    # Relationships
    enrollment = relationship("Enrollment", backref="schedules")
    instructor = relationship("Instructor", backref="schedules")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
