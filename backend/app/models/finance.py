"""
Financial ledger extensions: advance credits, exam-fee accounting, receipts.

All amounts are exact integer paise. Financial records are never deleted —
corrections are recorded as reversal/adjustment rows with reasons and audit.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class CreditLedgerEntry(Base):
    """Advance credits and their later application.

    Signed amounts: positive = credit added (an advance payment kept on the
    family account), negative = credit used against a charge. The balance is
    the sum of a student's rows — never a floating-point field.
    """

    __tablename__ = "credit_ledger"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True)

    kind = Column(String(20), nullable=False)  # advance | applied | refunded | adjustment
    amount_paise = Column(Integer, nullable=False)   # signed

    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)
    note = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ExamFee(Base):
    """Exam-fee accounting, kept separate from tuition.

    fee_charged_paise  — billed to the family (also issued as an exam invoice)
    academy_paid_paise — what the academy paid the exam provider (a cost, NOT
                         money received from the family)
    reimbursed_paise   — money received back from the family for that cost
    remaining reimbursement balance = academy_paid_paise - reimbursed_paise
    """

    __tablename__ = "exam_fees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True)
    exam_id = Column(UUID(as_uuid=True), nullable=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True)

    board = Column(String(80))            # Trinity, Rockschool, ...
    instrument = Column(String(80))
    grade_level = Column(String(40))
    exam_session = Column(String(80))

    fee_charged_paise = Column(Integer, default=0, nullable=False)
    academy_paid_paise = Column(Integer, default=0, nullable=False)
    reimbursed_paise = Column(Integer, default=0, nullable=False)
    reimbursement_method = Column(String(30))
    reimbursement_date = Column(Date)
    provider_reference = Column(String(120))

    attachment_stored_name = Column(String(80))
    attachment_filename = Column(String(255))
    attachment_content_type = Column(String(120))

    status = Column(String(24), default="open", nullable=False)
    # open | family_paid_first | academy_paid | reimbursed | settled
    notes = Column(Text)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Receipt(Base):
    """One receipt per verified payment. Never deleted."""

    __tablename__ = "receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, unique=True)
    receipt_number = Column(String(30), nullable=False, unique=True)
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    issued_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    notes = Column(Text)
