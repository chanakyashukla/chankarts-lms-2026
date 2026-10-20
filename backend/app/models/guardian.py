import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Guardian(Base):
    __tablename__ = "guardians"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    
    # Guardian Information
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    guardian_relationship = Column(String(50), nullable=False)  # parent, guardian, emergency_contact
    
    # Contact Information
    phone = Column(String(20), nullable=False)
    email = Column(String(255))
    address = Column(Text)
    
    # Additional Information
    is_primary = Column(String(1), default="N")  # Y/N - primary contact
    notes = Column(Text)
    
    # Relationships
    student = relationship("Student", back_populates="guardians")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def relationship(self) -> str:
        """Alias used by API schemas."""
        return self.guardian_relationship


class GuardianAccount(Base):
    """
    Links a parent/guardian user account to the student(s) they may access.

    A guardian account never grants access to unrelated students, and every
    portal request re-checks this relationship server-side.
    """

    __tablename__ = "guardian_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)

    relationship = Column(String(50), default="parent")  # parent, guardian
    is_primary = Column(String(1), default="Y")          # Y/N

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

