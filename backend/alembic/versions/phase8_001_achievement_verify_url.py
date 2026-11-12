"""Add achievements.verify_url — the awarding body's own verification page
(e.g. Trinity College London's certificate lookup), shown beside the
certificate in the portal so families can confirm the original.

Purely additive and nullable; no existing row is touched.

Revision ID: phase8_001
Revises: phase7_005
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "phase8_001"
down_revision: Union[str, None] = "phase7_005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name='achievements' AND column_name='verify_url'"
    )).scalar()
    if not exists:
        op.add_column("achievements",
                      sa.Column("verify_url", sa.String(length=500), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name='achievements' AND column_name='verify_url'"
    )).scalar()
    if exists:
        op.drop_column("achievements", "verify_url")
