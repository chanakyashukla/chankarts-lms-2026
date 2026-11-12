"""Add users.onboarding (interactive guided-tour state, server-side source of
truth so first-login introductions follow the account across devices).

Revision ID: phase7_005
Revises: phase7_004
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "phase7_005"
down_revision: Union[str, None] = "phase7_004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name='users' AND column_name='onboarding'"
    )).scalar()
    if not exists:
        op.add_column("users",
                      sa.Column("onboarding", sa.JSON(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    exists = bind.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.columns "
        "WHERE table_name='users' AND column_name='onboarding'"
    )).scalar()
    if exists:
        op.drop_column("users", "onboarding")
