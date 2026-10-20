"""Phase 2: Student Registration & Profiles

Revision ID: phase2_001
Revises: None
Create Date: 2026-09-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase2_001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("username", sa.String(100), unique=True, index=True, nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="student"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    
    # Create students table
    op.create_table(
        "students",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("cma_registration_id", sa.String(20), unique=True, index=True, nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("address", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("skill_level", sa.String(50)),
        sa.Column("profile_image_url", sa.String(500)),
        sa.Column("notes", sa.Text()),
        sa.Column("profile_complete", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    
    # Create instructors table
    op.create_table(
        "instructors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("specializations", sa.String(500)),
        sa.Column("qualifications", sa.String(500)),
        sa.Column("experience_years", sa.String(20)),
        sa.Column("profile_image_url", sa.String(500)),
        sa.Column("bio", sa.String(2000)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    
    # Create admins table
    op.create_table(
        "admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), unique=True, nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("admin_level", sa.String(50), server_default="admin"),
        sa.Column("profile_image_url", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    
    # Create guardians table
    op.create_table(
        "guardians",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("relationship", sa.String(50), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("address", sa.Text()),
        sa.Column("is_primary", sa.String(1), server_default="N"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_guardians_student_id", "guardians", ["student_id"])
    
    # Create instruments table
    op.create_table(
        "instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), unique=True, nullable=False),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("instrument_type", sa.String(20), nullable=False, server_default="instrument"),
        sa.Column("description", sa.String(500)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    
    # Create student_instruments table
    op.create_table(
        "student_instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("proficiency_level", sa.String(50)),
        sa.Column("is_primary", sa.String(1), server_default="N"),
        sa.Column("notes", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_student_instruments_student_id", "student_instruments", ["student_id"])
    op.create_index("ix_student_instruments_instrument_id", "student_instruments", ["instrument_id"])
    
    # Insert default instruments
    op.execute("""
        INSERT INTO instruments (id, name, display_name, instrument_type, description) VALUES
        (gen_random_uuid(), 'piano', 'Piano', 'instrument', 'Acoustic or digital piano'),
        (gen_random_uuid(), 'keyboard', 'Keyboard', 'instrument', 'Electronic keyboard'),
        (gen_random_uuid(), 'guitar', 'Guitar', 'instrument', 'Acoustic or electric guitar'),
        (gen_random_uuid(), 'violin', 'Violin', 'instrument', 'Acoustic violin'),
        (gen_random_uuid(), 'ukulele', 'Ukulele', 'instrument', 'Hawaiian ukulele'),
        (gen_random_uuid(), 'western_vocals', 'Western Vocals', 'discipline', 'Western vocal training'),
        (gen_random_uuid(), 'indian_classical_vocals', 'Indian Classical Vocals', 'discipline', 'Indian classical vocal training'),
        (gen_random_uuid(), 'music_theory', 'Music Theory', 'discipline', 'Foundation music theory'),
        (gen_random_uuid(), 'bansuri', 'Bansuri', 'instrument', 'Indian bamboo flute'),
        (gen_random_uuid(), 'electronic_keyboard', 'Electronic Keyboard', 'instrument', 'Trinity/Rockschool electronic keyboard')
    """)


def downgrade() -> None:
    op.drop_table("student_instruments")
    op.drop_table("instruments")
    op.drop_table("guardians")
    op.drop_table("admins")
    op.drop_table("instructors")
    op.drop_table("students")
    op.drop_table("users")
