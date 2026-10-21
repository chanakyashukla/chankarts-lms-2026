import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Date, ForeignKey, Text, Integer, Boolean, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class FeePackage(Base):
    """
    Configurable fee package. Money is stored as integer paise.

    Current academy standard options (seeded, not hard-coded elsewhere):
      - 4 classes / month  -> 450000 paise (₹4,500)
      - 8 classes / month  -> 800000 paise (₹8,000)
    Legacy packages may exist per student agreement and are never overwritten.
    """

    __tablename__ = "fee_packages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(120), nullable=False)
    code = Column(String(40), unique=True, nullable=False)   # e.g. standard_4, standard_8, legacy_*
    sessions_included = Column(Integer, nullable=False)
    fee_paise = Column(Integer, nullable=False)              # integer-safe currency
    currency = Column(String(8), default="INR", nullable=False)
    billing_period = Column(String(20), default="monthly", nullable=False)
    session_duration_minutes = Column(Integer, default=60, nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)
    is_legacy = Column(Boolean, default=False, nullable=False)  # individually agreed rates

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Invoice(Base):
    """Issued invoice for one enrollment + billing month. Never mutated after issue."""

    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_number = Column(String(30), unique=True, nullable=False, index=True)  # CMA/INV/YYYY/MMMM

    fee_record_id = Column(UUID(as_uuid=True), ForeignKey("fee_records.id", ondelete="SET NULL"), nullable=True, index=True)
    # nullable so permanent student deletion can RETAIN the invoice with the
    # student/enrollment link released (documented financial-retention strategy)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True)
    package_id = Column(UUID(as_uuid=True), ForeignKey("fee_packages.id", ondelete="SET NULL"), nullable=True)

    billing_month = Column(String(7), nullable=False, index=True)  # YYYY-MM
    # tuition | exam | other — exam charges stay separable in reports while
    # still appearing on the student's financial statement
    charge_type = Column(String(20), default="tuition", nullable=False)
    description = Column(Text)
    amount_paise = Column(Integer, nullable=False)
    currency = Column(String(8), default="INR", nullable=False)
    amount_paid_paise = Column(Integer, default=0, nullable=False)

    status = Column(String(20), default="pending", nullable=False, index=True)  # pending, partially_paid, paid, void
    due_date = Column(Date)

    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    notes = Column(Text)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("enrollment_id", "billing_month", name="uq_invoice_enrollment_month"),
    )


class PaymentOrder(Base):
    """Server-side payment order (Razorpay order) tied to one invoice."""

    __tablename__ = "payment_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(String(64), unique=True, nullable=False, index=True)  # provider order id
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)

    amount_paise = Column(Integer, nullable=False)
    currency = Column(String(8), default="INR", nullable=False)
    status = Column(String(24), default="created", nullable=False)  # created, paid, failed, expired, cancelled
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class Payment(Base):
    """A verified (or manually recorded) payment. Ledger updates reference this."""

    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    provider = Column(String(24), default="razorpay", nullable=False)  # razorpay, manual, bank, upi, cash
    provider_payment_id = Column(String(64), index=True)               # e.g. pay_XXXX (nullable for manual)
    order_id = Column(String(64), index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)

    # A family payment may cover several students; payer_user_id records who paid
    payer_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    payer_name = Column(String(200))

    amount_paise = Column(Integer, nullable=False)
    currency = Column(String(8), default="INR", nullable=False)
    method = Column(String(30))              # upi, card, netbanking, wallet, cash, bank_transfer
    status = Column(String(20), default="verified", nullable=False)  # pending_verification, verified, failed, refunded, disputed

    paid_at = Column(DateTime)
    verified_at = Column(DateTime)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))  # manual reconciliation operator
    notes = Column(Text)
    # receipt_number: issued with the receipt; source records how the money
    # arrived — manual entries are admin-recorded, not independently verified
    # bank transactions
    receipt_number = Column(String(30))
    source = Column(String(20), default="manual")  # manual | online | button

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_ref"),
    )


class PaymentAllocation(Base):
    """
    Explicit, auditable allocation of a payment across student ledgers.

    A combined family payment (e.g. Hosangadi parent) is allocated to one or
    both students here — both accounts are never auto-marked paid.
    """

    __tablename__ = "payment_allocations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    enrollment_id = Column(UUID(as_uuid=True), ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True)

    amount_paise = Column(Integer, nullable=False)
    allocated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    allocated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Corrections preserve history: a reversing allocation points at the original
    reverses_allocation_id = Column(UUID(as_uuid=True), ForeignKey("payment_allocations.id", ondelete="SET NULL"), nullable=True)
    reason = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class PaymentEvent(Base):
    """Raw provider events (webhooks). `event_id` is unique => idempotent replay."""

    __tablename__ = "payment_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id = Column(String(80), unique=True, nullable=False, index=True)  # provider event id
    event_type = Column(String(60), nullable=False)                         # payment.captured, payment.failed, ...

    signature_valid = Column(Boolean, default=False, nullable=False)
    processing_status = Column(String(24), default="received", nullable=False)  # received, processed, ignored, failed
    error_detail = Column(Text)
    payload_digest = Column(String(64))   # sha256 of raw body; never store full secrets
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)

    received_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime)
