import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class InstrumentType(str):
    INSTRUMENT = "instrument"
    DISCIPLINE = "discipline"


class Instrument(Base):
    __tablename__ = "instruments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Instrument Information
    name = Column(String(100), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    instrument_type = Column(String(20), nullable=False, default=InstrumentType.INSTRUMENT)  # instrument or discipline
    description = Column(String(500))
    
    # Status
    is_active = Column(Boolean, default=True)
    
    # Relationships
    student_instruments = relationship("StudentInstrument", back_populates="instrument")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class StudentInstrument(Base):
    __tablename__ = "student_instruments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    instrument_id = Column(UUID(as_uuid=True), ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False)
    
    # Additional Information
    proficiency_level = Column(String(50))  # beginner, intermediate, advanced
    is_primary = Column(String(1), default="N")  # Y/N - primary instrument
    notes = Column(String(500))
    
    # Relationships
    student = relationship("Student", back_populates="student_instruments")
    instrument = relationship("Instrument", back_populates="student_instruments")
    
    created_at = Column(DateTime, default=datetime.utcnow)
