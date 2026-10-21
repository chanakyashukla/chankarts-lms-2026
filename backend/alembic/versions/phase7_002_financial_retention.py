"""Permanent-delete financial retention: release student/enrollment links.

Permanent student deletion must RETAIN financial records (invoices, fee
records, credit ledger, payment allocations, exam fees) for accounting while
freeing the student's unique identifiers.  This migration:

1. makes the student_id/enrollment_id links on those tables nullable, and
2. normalises their FK actions to ON DELETE SET NULL (some production FKs were
   created as CASCADE/NO ACTION by earlier schema eras).

Reversible: down() restores NOT NULL + CASCADE (only safe when no NULL links
exist).

Revision ID: phase7_002
Revises: phase7_001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "phase7_002"
down_revision: Union[str, None] = "phase7_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, referenced_table)
TARGETS = [
    ("invoices", "student_id", "students"),
    ("invoices", "enrollment_id", "enrollments"),
    ("fee_records", "student_id", "students"),
    ("fee_records", "enrollment_id", "enrollments"),
    ("payment_allocations", "student_id", "students"),
    ("payment_allocations", "enrollment_id", "enrollments"),
    ("credit_ledger", "student_id", "students"),
    ("exam_fees", "student_id", "students"),
]


def _fk_name(bind, table: str, column: str, ref_table: str) -> str | None:
    row = bind.execute(
        sa.text(
            """
            SELECT c.conname FROM pg_constraint c
            JOIN pg_attribute a ON a.attrelid = c.conrelid
            JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum, ord) ON a.attnum = k.attnum
            WHERE c.contype = 'f'
              AND c.conrelid = to_regclass(:t)
              AND c.confrelid = to_regclass(:r)
              AND a.attname = :col
            LIMIT 1
            """
        ),
        {"t": table, "r": ref_table, "col": column},
    ).first()
    return row[0] if row else None


def _table_exists(bind, table: str) -> bool:
    return bind.execute(
        sa.text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table}
    ).scalar()


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, ref_table in TARGETS:
        if not _table_exists(bind, table):
            continue
        fk = _fk_name(bind, table, column, ref_table)
        if fk:
            op.drop_constraint(fk, table, type_="foreignkey")
        op.alter_column(table, column, existing_type=sa.UUID(), nullable=True)
        op.create_foreign_key(
            f"{table}_{column}_setnull_fkey", table, ref_table,
            [column], ["id"], ondelete="SET NULL",
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table, column, ref_table in reversed(TARGETS):
        if not _table_exists(bind, table):
            continue
        # refuse to re-tighten while NULL links exist (data safety)
        nulls = bind.execute(
            sa.text(f'SELECT COUNT(*) FROM {table} WHERE "{column}" IS NULL')
        ).scalar()
        if nulls:
            raise RuntimeError(
                f"downgrade blocked: {nulls} NULL {table}.{column} link(s) exist"
            )
        fk = _fk_name(bind, table, column, ref_table)
        if fk:
            op.drop_constraint(fk, table, type_="foreignkey")
        op.alter_column(table, column, existing_type=sa.UUID(), nullable=False)
        op.create_foreign_key(
            f"{table}_{column}_fkey", table, ref_table,
            [column], ["id"], ondelete="CASCADE",
        )
