"""Phase 4: Admin Dashboard Tables (enrollments, fees, attendance, progress, schedules)

Revision ID: phase4_001
Revises: phase3_001
Create Date: 2026-09-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase4_001"
down_revision: Union[str, None] = "phase3_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("programme_id", sa.String(50), nullable=False),
        sa.Column("programme_name", sa.String(100), nullable=False),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("instructors.id"), nullable=True),
        sa.Column("fee_plan", sa.String(20)),
        sa.Column("fee_amount", sa.Numeric(10, 2)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])
    op.create_index("ix_enrollments_status", "enrollments", ["status"])

    op.create_table(
        "fee_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fee_plan", sa.String(20), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("amount_expected", sa.Numeric(10, 2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(10, 2), server_default="0"),
        sa.Column("payment_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("payment_date", sa.Date()),
        sa.Column("payment_method", sa.String(50)),
        sa.Column("transaction_ref", sa.String(100)),
        sa.Column("notes", sa.Text()),
        sa.Column("is_complimentary", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_fee_records_student_id", "fee_records", ["student_id"])
    op.create_index("ix_fee_records_enrollment_id", "fee_records", ["enrollment_id"])
    op.create_index("ix_fee_records_payment_status", "fee_records", ["payment_status"])

    op.create_table(
        "class_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("instructors.id"), nullable=False),
        sa.Column("day_of_week", sa.String(10), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("frequency", sa.String(20), server_default="weekly"),
        sa.Column("is_online", sa.Boolean(), server_default="false"),
        sa.Column("location", sa.String(200)),
        sa.Column("meeting_link", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_class_schedules_enrollment_id", "class_schedules", ["enrollment_id"])

    op.create_table(
        "attendance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("instructors.id"), nullable=False),
        sa.Column("class_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_attendance_enrollment_id", "attendance", ["enrollment_id"])
    op.create_index("ix_attendance_student_id", "attendance", ["student_id"])
    op.create_index("ix_attendance_class_date", "attendance", ["class_date"])

    op.create_table(
        "progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instructor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("instructors.id"), nullable=False),
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("topics_covered", sa.Text()),
        sa.Column("progress_summary", sa.Text()),
        sa.Column("practice_notes", sa.Text()),
        sa.Column("instructor_remarks", sa.Text()),
        sa.Column("next_month_focus", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_progress_enrollment_id", "progress", ["enrollment_id"])
    op.create_index("ix_progress_student_id", "progress", ["student_id"])


def downgrade() -> None:
    op.drop_table("progress")
    op.drop_table("attendance")
    op.drop_table("class_schedules")
    op.drop_table("fee_records")
    op.drop_table("enrollments")
