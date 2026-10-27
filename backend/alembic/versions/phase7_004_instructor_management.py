"""Instructor management & payout foundation (additive + FK normalization).

1. Normalise FKs → instructors to ON DELETE SET NULL (history survives
   instructor deletion; class_sessions must NOT cascade completed rows away),
   dropping NOT NULL where the schema era forced it (attendance,
   class_schedules, progress).
2. instructors: employment/compensation columns.
3. New append-only tables: instructor_rate_rules, instructor_payouts,
   instructor_month_reviews.

Revision ID: phase7_004
Revises: phase7_003
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "phase7_004"
down_revision: Union[str, None] = "phase7_003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_TARGETS = [
    "attendance",
    "class_schedules",
    "class_sessions",
    "enrollments",
    "progress",
    "monthly_reports",
    "student_syllabus_assignments",
]


def _col_exists(bind, table: str, column: str) -> bool:
    return bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c"), {"t": table, "c": column}).scalar() > 0


def _fk_name(bind, table: str, column: str):
    row = bind.execute(sa.text(
        """
        SELECT c.conname FROM pg_constraint c
        JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum, ord) ON true
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.contype = 'f' AND c.conrelid = to_regclass(:t)
          AND c.confrelid = to_regclass('instructors')
          AND a.attname = :col
        LIMIT 1
        """), {"t": table, "col": column}).first()
    return row[0] if row else None


def _fk_state(bind, table: str, column: str):
    row = bind.execute(sa.text(
        """
        SELECT c.confdeltype, a.attnotnull FROM pg_constraint c
        JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum, ord) ON true
        JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
        WHERE c.contype = 'f' AND c.conrelid = to_regclass(:t)
          AND c.confrelid = to_regclass('instructors')
          AND a.attname = :col
        LIMIT 1
        """), {"t": table, "col": column}).first()
    return (row[0].decode() if isinstance(row[0], bytes) else row[0], bool(row[1])) if row else (None, None)


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1) FKs → instructors: SET NULL + nullable ---
    for table in FK_TARGETS:
        if not _col_exists(bind, table, "instructor_id"):
            continue
        deltype, notnull = _fk_state(bind, table, "instructor_id")
        if deltype is None:
            continue
        if notnull:
            op.execute(sa.text(
                f'ALTER TABLE {table} ALTER COLUMN instructor_id DROP NOT NULL'))
        if deltype != "n":
            fk = _fk_name(bind, table, "instructor_id")
            if fk:
                op.drop_constraint(fk, table, type_="foreignkey")
            op.create_foreign_key(
                f"{table}_instructor_id_setnull_fkey", table, "instructors",
                ["instructor_id"], ["id"], ondelete="SET NULL")

    # --- 2) instructors employment/compensation columns ---
    if not _col_exists(bind, "instructors", "employment_type"):
        op.add_column("instructors", sa.Column("employment_type", sa.String(40), nullable=True))
    if not _col_exists(bind, "instructors", "compensation_mode"):
        op.add_column("instructors", sa.Column("compensation_mode", sa.String(40),
                                                nullable=False, server_default="per_completed_class"))
    if not _col_exists(bind, "instructors", "per_class_rate_paise"):
        op.add_column("instructors", sa.Column("per_class_rate_paise", sa.Integer(), nullable=True))
    if not _col_exists(bind, "instructors", "rate_effective_date"):
        op.add_column("instructors", sa.Column("rate_effective_date", sa.Date(), nullable=True))
    if not _col_exists(bind, "instructors", "contract_notes"):
        op.add_column("instructors", sa.Column("contract_notes", sa.Text(), nullable=True))

    # --- 3) payout tables ---
    if not _col_exists(bind, "instructor_rate_rules", "id"):
        op.create_table(
            "instructor_rate_rules",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("instructor_id", sa.Uuid(), sa.ForeignKey("instructors.id", ondelete="CASCADE"), nullable=True),
            sa.Column("category", sa.String(40), nullable=True),
            sa.Column("per_class_rate_paise", sa.Integer(), nullable=False),
            sa.Column("effective_from", sa.Date(), nullable=False),
            sa.Column("notes", sa.Text()),
            sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("instructor_id IS NOT NULL OR category IS NOT NULL", name="ck_rate_rule_scope"),
        )
        op.create_index("ix_instructor_rate_rules_instructor_id", "instructor_rate_rules", ["instructor_id"])
        op.create_index("ix_instructor_rate_rules_category", "instructor_rate_rules", ["category"])

    if not _col_exists(bind, "instructor_payouts", "id"):
        op.create_table(
            "instructor_payouts",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("instructor_id", sa.Uuid(), sa.ForeignKey("instructors.id", ondelete="SET NULL"), nullable=True),
            sa.Column("month", sa.String(7), nullable=False),
            sa.Column("amount_paise", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False, server_default="payout"),
            sa.Column("status", sa.String(16), nullable=False, server_default="recorded"),
            sa.Column("paid_at", sa.Date()),
            sa.Column("method", sa.String(30)),
            sa.Column("reference", sa.String(120)),
            sa.Column("notes", sa.Text()),
            sa.Column("reversal_of", sa.Uuid(), sa.ForeignKey("instructor_payouts.id", ondelete="SET NULL")),
            sa.Column("recorded_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_instructor_payouts_instructor_id", "instructor_payouts", ["instructor_id"])
        op.create_index("ix_instructor_payouts_month", "instructor_payouts", ["month"])

    if not _col_exists(bind, "instructor_month_reviews", "id"):
        op.create_table(
            "instructor_month_reviews",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("instructor_id", sa.Uuid(), sa.ForeignKey("instructors.id", ondelete="CASCADE"), nullable=False),
            sa.Column("month", sa.String(7), nullable=False),
            sa.Column("payable_at_review", sa.Integer(), nullable=False),
            sa.Column("reviewed_by", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL")),
            sa.Column("reviewed_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("instructor_id", "month", name="uq_instructor_month_review"),
        )
        op.create_index("ix_instructor_month_reviews_instructor_id", "instructor_month_reviews", ["instructor_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if _col_exists(bind, "instructor_month_reviews", "id"):
        op.drop_table("instructor_month_reviews")
    if _col_exists(bind, "instructor_payouts", "id"):
        op.drop_table("instructor_payouts")
    if _col_exists(bind, "instructor_rate_rules", "id"):
        op.drop_table("instructor_rate_rules")
    for col in ("contract_notes", "rate_effective_date", "per_class_rate_paise",
                "compensation_mode", "employment_type"):
        if _col_exists(bind, "instructors", col):
            op.drop_column("instructors", col)
    # FK states are intentionally not reverted to CASCADE (destructive)
