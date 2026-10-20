"""Phase 7: Student remarks with explicit visibility

Revision ID: phase7_001
Revises: phase5_001
Create Date: 2026-10-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase7_001"
down_revision: Union[str, None] = "phase5_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_remarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("enrollments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_role", sa.String(20)),
        sa.Column("visibility", sa.String(20), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_student_remarks_student_id", "student_remarks", ["student_id"])
    op.create_index("ix_student_remarks_enrollment_id", "student_remarks", ["enrollment_id"])


def downgrade() -> None:
    op.drop_index("ix_student_remarks_enrollment_id", table_name="student_remarks")
    op.drop_index("ix_student_remarks_student_id", table_name="student_remarks")
    op.drop_table("student_remarks")
