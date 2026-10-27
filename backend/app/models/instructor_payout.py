import uuid
from datetime import datetime, date

from sqlalchemy import Column, String, Integer, Date, DateTime, Text, ForeignKey, UniqueConstraint, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class InstructorRateRule(Base):
    """Per-class rate with an effective date.

    Scope: instructor_id set  → individual agreed rate (takes precedence)
           instructor_id NULL → category default policy (category set)
    Rows are append-only: a rate change adds a new effective_from row, so
    historical payouts always resolve the rate that applied at the time.
    """
    __tablename__ = "instructor_rate_rules"
    __table_args__ = (
        CheckConstraint("instructor_id IS NOT NULL OR category IS NOT NULL",
                        name="ck_rate_rule_scope"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id", ondelete="CASCADE"),
                           nullable=True, index=True)
    category = Column(String(40), nullable=True, index=True)   # intern|part_time|regular|contract
    per_class_rate_paise = Column(Integer, nullable=False)
    effective_from = Column(Date, nullable=False)
    notes = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class InstructorPayout(Base):
    """An actual money transfer recorded by an administrator (or an explicit
    adjustment). The payable itself is always computed from completed
    sessions — never stored — so it cannot drift."""
    __tablename__ = "instructor_payouts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id", ondelete="SET NULL"),
                           nullable=True, index=True)
    month = Column(String(7), nullable=False, index=True)              # YYYY-MM
    amount_paise = Column(Integer, nullable=False)                     # negative for adjustments
    kind = Column(String(16), default="payout", nullable=False)        # payout | adjustment
    status = Column(String(16), default="recorded", nullable=False)    # recorded | reversed
    paid_at = Column(Date, nullable=True)
    method = Column(String(30), nullable=True)
    reference = Column(String(120), nullable=True)
    notes = Column(Text)
    reversal_of = Column(UUID(as_uuid=True), ForeignKey("instructor_payouts.id", ondelete="SET NULL"),
                         nullable=True)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class InstructorMonthReview(Base):
    """Administrator sign-off of one instructor-month payout calculation."""
    __tablename__ = "instructor_month_reviews"
    __table_args__ = (
        UniqueConstraint("instructor_id", "month", name="uq_instructor_month_review"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("instructors.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    month = Column(String(7), nullable=False)
    payable_at_review = Column(Integer, nullable=False)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
