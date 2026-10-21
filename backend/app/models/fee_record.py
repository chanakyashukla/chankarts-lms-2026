import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Text, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class PaymentStatus(str):
    PENDING = "pending"
    PAID = "paid"
    PARTIAL = "partial"
    OVERDUE = "overdue"
    WAIVED = "waived"


class FeeRecord(Base):
    __tablename__ = "fee_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Links (nullable + SET NULL: permanent student deletion retains the fee
    # record for accounting while releasing the student/enrollment identifiers)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="SET NULL"), nullable=True)
    
    # Fee details
    fee_plan = Column(String(20), nullable=False)  # 4_classes, 8_classes
    period = Column(String(20), nullable=False)  # MM-YYYY
    amount_expected = Column(Numeric(10, 2), nullable=False)
    amount_paid = Column(Numeric(10, 2), default=0)
    payment_status = Column(String(20), default=PaymentStatus.PENDING, nullable=False)
    
    # Payment info
    payment_date = Column(Date)
    payment_method = Column(String(50))  # cash, upi, bank_transfer, card
    transaction_ref = Column(String(100))
    
    # Notes
    notes = Column(Text)
    is_complimentary = Column(Boolean, default=False)  # 5th class complimentary
    
    # Relationships
    enrollment = relationship("Enrollment", backref="fee_records")
    student = relationship("Student", backref="fee_records")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
