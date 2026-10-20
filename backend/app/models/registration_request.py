import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, String, DateTime, Date, Boolean, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class RegistrationRequestStatus(str):
    PENDING = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_INFO = "needs_information"


class RegistrationRequest(Base):
    __tablename__ = "registration_requests"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Request tracking
    request_id = Column(String(20), unique=True, index=True, nullable=False)  # REQ-YYYY-####
    status = Column(String(30), default=RegistrationRequestStatus.PENDING, nullable=False)
    
    # Account information (from registration form)
    full_name = Column(String(200), nullable=False)
    email = Column(String(255), nullable=False)
    mobile = Column(String(20), nullable=False)
    
    # Student details
    date_of_birth = Column(Date, nullable=False)
    is_minor = Column(Boolean, default=False)
    address = Column(Text)
    
    # Guardian information (for minors)
    guardian_name = Column(String(200))
    guardian_relationship = Column(String(50))
    guardian_email = Column(String(255))
    guardian_mobile = Column(String(20))
    
    # Selected programmes (JSON array of programme objects)
    selected_programmes = Column(JSON, nullable=False)  # [{"id": "piano", "name": "Piano"}, ...]
    
    # Admin review
    reviewed_by = Column(UUID(as_uuid=True))  # admin user id
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    
    # 72-hour review window
    review_deadline = Column(DateTime)  # submitted_at + 72 hours
    
    # Linked student (after approval)
    student_id = Column(UUID(as_uuid=True))  # links to students table after approval
    
    # Metadata
    submitted_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
