import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, Text, ForeignKey, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Instructor(Base):
    __tablename__ = "instructors"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    
    # Professional Information
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    phone = Column(String(20))
    
    # Music Expertise (will be relational in Phase 3)
    specializations = Column(String(500))  # Comma-separated for now
    qualifications = Column(String(500))  # Comma-separated for now
    experience_years = Column(String(20))
    
    # Profile
    profile_image_url = Column(String(500))
    bio = Column(String(2000))
    is_active = Column(Boolean, default=True)

    # Scheduling: admin-configured travel buffer (minutes) applied between
    # consecutive OFFLINE classes. NULL = travel cannot be confirmed
    # (availability then reports "requires clarification" instead of guessing).
    travel_buffer_minutes = Column(Integer, nullable=True)

    # Employment / engagement + compensation (per completed class, INR paise).
    # Category defaults live in instructor_rate_rules; per_class_rate_paise
    # here is NULL until an individual agreed rate is configured.
    employment_type = Column(String(40), nullable=True)          # intern|part_time|regular|contract
    compensation_mode = Column(String(40), default="per_completed_class", nullable=False)
    per_class_rate_paise = Column(Integer, nullable=True)
    rate_effective_date = Column(Date, nullable=True)
    contract_notes = Column(Text, nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="instructor_profile")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
