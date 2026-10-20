import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean
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
    
    # Relationships
    user = relationship("User", back_populates="instructor_profile")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
