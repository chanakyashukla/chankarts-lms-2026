import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Token data (hashed)
    token_hash = Column(String(255), unique=True, index=True, nullable=False)
    
    # Link to registration request
    registration_request_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Email being verified
    email = Column(String(255), nullable=False)
    
    # Status
    is_used = Column(Boolean, default=False, nullable=False)
    
    # Expiry (24 hours)
    expires_at = Column(DateTime, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    used_at = Column(DateTime)
