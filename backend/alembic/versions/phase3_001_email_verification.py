"""Phase 3: Email Verification Tokens

Revision ID: phase3_001
Revises: phase2_001
Create Date: 2026-09-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase3_001"
down_revision: Union[str, None] = "phase2_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create registration_requests table if not exists
    op.execute("""
        CREATE TABLE IF NOT EXISTS registration_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            request_id VARCHAR(20) UNIQUE NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending_review',
            full_name VARCHAR(200) NOT NULL,
            email VARCHAR(255) NOT NULL,
            mobile VARCHAR(20) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            date_of_birth DATE NOT NULL,
            is_minor BOOLEAN DEFAULT FALSE,
            address TEXT,
            guardian_name VARCHAR(200),
            guardian_relationship VARCHAR(50),
            guardian_email VARCHAR(255),
            guardian_mobile VARCHAR(20),
            selected_programmes JSONB NOT NULL,
            reviewed_by UUID,
            reviewed_at TIMESTAMP,
            review_notes TEXT,
            review_deadline TIMESTAMP,
            student_id UUID,
            submitted_at TIMESTAMP NOT NULL DEFAULT NOW(),
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_registration_requests_request_id ON registration_requests(request_id)")
    
    # Create email_verification_tokens table
    op.create_table(
        "email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("registration_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("is_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("used_at", sa.DateTime()),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_verification_tokens_registration_request_id ON email_verification_tokens(registration_request_id)")


def downgrade() -> None:
    op.drop_table("email_verification_tokens")
    op.execute("DROP TABLE IF EXISTS registration_requests")
