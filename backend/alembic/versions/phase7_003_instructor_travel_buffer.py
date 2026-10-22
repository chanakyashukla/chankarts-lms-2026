"""Add instructors.travel_buffer_minutes (admin-configured travel time between
offline classes; NULL means availability cannot be confirmed).

Revision ID: phase7_003
Revises: phase7_002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "phase7_003"
down_revision: Union[str, None] = "phase7_002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name='instructors' AND column_name='travel_buffer_minutes'"
    )).scalar()
    if not exists:
        op.add_column("instructors",
                      sa.Column("travel_buffer_minutes", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name='instructors' AND column_name='travel_buffer_minutes'"
    )).scalar()
    if exists:
        op.drop_column("instructors", "travel_buffer_minutes")
