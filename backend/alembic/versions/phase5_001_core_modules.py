"""Phase 5: Core LMS modules

- guardian accounts (parent portal links)
- audit events + notifications
- class sessions + status history (no absence status anywhere)
- fee packages, invoices, payments, allocations, webhook events
- assignments, submissions, study materials, recommendations
- syllabus engine, monthly reports, exams and milestones
- students.portal_slug for personalised routes

Revision ID: phase5_001
Revises: phase4_001
Create Date: 2026-10-14
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "phase5_001"
down_revision: Union[str, None] = "phase4_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # students.portal_slug
    # ------------------------------------------------------------------
    op.add_column("students", sa.Column("portal_slug", sa.String(120), nullable=True))
    op.create_index("ix_students_portal_slug", "students", ["portal_slug"], unique=True)

    # ------------------------------------------------------------------
    # Guardian accounts (parent login ↔ linked students)
    # ------------------------------------------------------------------
    op.create_table(
        "guardian_accounts",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship", sa.String(50), server_default="parent"),
        sa.Column("is_primary", sa.String(1), server_default="Y"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_guardian_accounts_user_id", "guardian_accounts", ["user_id"])
    op.create_index("ix_guardian_accounts_student_id", "guardian_accounts", ["student_id"])

    # ------------------------------------------------------------------
    # Audit + notifications
    # ------------------------------------------------------------------
    op.create_table(
        "audit_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_role", sa.String(20)),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("entity_type", sa.String(60), nullable=False),
        sa.Column("entity_id", sa.String(64)),
        sa.Column("summary", sa.Text()),
        sa.Column("before_data", postgresql.JSON()),
        sa.Column("after_data", postgresql.JSON()),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"])

    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("channel", sa.String(20), server_default="in_app"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("dedupe_key", sa.String(160)),
        sa.Column("related_entity_type", sa.String(60)),
        sa.Column("related_entity_id", sa.String(64)),
        sa.Column("sent_at", sa.DateTime()),
        sa.Column("read_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_dedupe_key", "notifications", ["dedupe_key"], unique=True)

    # ------------------------------------------------------------------
    # Class sessions (green / amber / red — never "absent")
    # ------------------------------------------------------------------
    op.create_table(
        "class_sessions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instructor_id", UUID, sa.ForeignKey("instructors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("scheduled_start", sa.Time(), nullable=False),
        sa.Column("scheduled_end", sa.Time(), nullable=False),
        sa.Column("timezone", sa.String(40), nullable=False, server_default="Asia/Kolkata"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("actual_date", sa.Date()),
        sa.Column("actual_start", sa.Time()),
        sa.Column("actual_end", sa.Time()),
        sa.Column("actual_duration_minutes", sa.Integer()),
        sa.Column("status", sa.String(30), nullable=False, server_default="scheduled"),
        sa.Column("topics_covered", sa.Text()),
        sa.Column("faculty_remarks", sa.Text()),
        sa.Column("reschedule_reason", sa.Text()),
        sa.Column("replaces_session_id", UUID, sa.ForeignKey("class_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_duration_exception", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("exception_note", sa.Text()),
        sa.Column("counts_toward_package", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("billing_month", sa.String(7)),
        sa.Column("is_online", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("location", sa.String(200)),
        sa.Column("meeting_link", sa.String(500)),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_class_sessions_enrollment_id", "class_sessions", ["enrollment_id"])
    op.create_index("ix_class_sessions_student_id", "class_sessions", ["student_id"])
    op.create_index("ix_class_sessions_instructor_id", "class_sessions", ["instructor_id"])
    op.create_index("ix_class_sessions_scheduled_date", "class_sessions", ["scheduled_date"])
    op.create_index("ix_class_sessions_status", "class_sessions", ["status"])
    op.create_index("ix_class_sessions_replaces", "class_sessions", ["replaces_session_id"])

    op.create_table(
        "session_status_history",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("session_id", UUID, sa.ForeignKey("class_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("changed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("changed_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_session_status_history_session_id", "session_status_history", ["session_id"])

    # ------------------------------------------------------------------
    # Billing
    # ------------------------------------------------------------------
    op.create_table(
        "fee_packages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("sessions_included", sa.Integer(), nullable=False),
        sa.Column("fee_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("billing_period", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("session_duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_legacy", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "invoices",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("invoice_number", sa.String(30), nullable=False, unique=True),
        sa.Column("fee_record_id", UUID, sa.ForeignKey("fee_records.id", ondelete="SET NULL"), nullable=True),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package_id", UUID, sa.ForeignKey("fee_packages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("billing_month", sa.String(7), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("amount_paid_paise", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("due_date", sa.Date()),
        sa.Column("issued_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("enrollment_id", "billing_month", name="uq_invoice_enrollment_month"),
    )
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])
    op.create_index("ix_invoices_enrollment_id", "invoices", ["enrollment_id"])
    op.create_index("ix_invoices_student_id", "invoices", ["student_id"])
    op.create_index("ix_invoices_billing_month", "invoices", ["billing_month"])
    op.create_index("ix_invoices_status", "invoices", ["status"])

    op.create_table(
        "payment_orders",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("order_id", sa.String(64), nullable=False, unique=True),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("requested_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payment_orders_order_id", "payment_orders", ["order_id"])
    op.create_index("ix_payment_orders_invoice_id", "payment_orders", ["invoice_id"])

    op.create_table(
        "payments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("provider", sa.String(24), nullable=False, server_default="razorpay"),
        sa.Column("provider_payment_id", sa.String(64)),
        sa.Column("order_id", sa.String(64)),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payer_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payer_name", sa.String(200)),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("method", sa.String(30)),
        sa.Column("status", sa.String(20), nullable=False, server_default="verified"),
        sa.Column("paid_at", sa.DateTime()),
        sa.Column("verified_at", sa.DateTime()),
        sa.Column("recorded_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_payment_provider_ref"),
    )
    op.create_index("ix_payments_provider_payment_id", "payments", ["provider_payment_id"])
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])

    op.create_table(
        "payment_allocations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("payment_id", UUID, sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount_paise", sa.Integer(), nullable=False),
        sa.Column("allocated_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("allocated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("reverses_allocation_id", UUID, sa.ForeignKey("payment_allocations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"])
    op.create_index("ix_payment_allocations_invoice_id", "payment_allocations", ["invoice_id"])
    op.create_index("ix_payment_allocations_student_id", "payment_allocations", ["student_id"])

    op.create_table(
        "payment_events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("event_id", sa.String(80), nullable=False, unique=True),
        sa.Column("event_type", sa.String(60), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("processing_status", sa.String(24), nullable=False, server_default="received"),
        sa.Column("error_detail", sa.Text()),
        sa.Column("payload_digest", sa.String(64)),
        sa.Column("payment_id", UUID, sa.ForeignKey("payments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("received_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime()),
    )
    op.create_index("ix_payment_events_event_id", "payment_events", ["event_id"])

    # Seed standard academy packages (idempotent)
    op.execute(
        """
        INSERT INTO fee_packages (id, name, code, sessions_included, fee_paise, currency, billing_period,
                                  session_duration_minutes, description, is_active, is_legacy)
        SELECT gen_random_uuid(), '4 Classes Package', 'standard_4', 4, 450000, 'INR', 'monthly', 60,
               'Four 1-hour classes per month, access to study material and a monthly faculty report.',
               true, false
        WHERE NOT EXISTS (SELECT 1 FROM fee_packages WHERE code = 'standard_4')
        """
    )
    op.execute(
        """
        INSERT INTO fee_packages (id, name, code, sessions_included, fee_paise, currency, billing_period,
                                  session_duration_minutes, description, is_active, is_legacy)
        SELECT gen_random_uuid(), '8 Classes Package', 'standard_8', 8, 800000, 'INR', 'monthly', 60,
               'Eight 1-hour classes per month, access to study material and a monthly faculty report.',
               true, false
        WHERE NOT EXISTS (SELECT 1 FROM fee_packages WHERE code = 'standard_8')
        """
    )

    # ------------------------------------------------------------------
    # Learning
    # ------------------------------------------------------------------
    op.create_table(
        "assignments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("instructions", sa.Text()),
        sa.Column("practice_notes", sa.Text()),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("priority", sa.String(12), server_default="normal"),
        sa.Column("status", sa.String(20), nullable=False, server_default="assigned"),
        sa.Column("allow_audio", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assignments_enrollment_id", "assignments", ["enrollment_id"])
    op.create_index("ix_assignments_student_id", "assignments", ["student_id"])
    op.create_index("ix_assignments_due_date", "assignments", ["due_date"])

    op.create_table(
        "submissions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("assignment_id", UUID, sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="submitted"),
        sa.Column("submitted_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("feedback", sa.Text()),
        sa.Column("reviewed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_submissions_assignment_id", "submissions", ["assignment_id"])
    op.create_index("ix_submissions_student_id", "submissions", ["student_id"])

    op.create_table(
        "assignment_files",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("assignment_id", UUID, sa.ForeignKey("assignments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("submission_id", UUID, sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("owner_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("owner_role", sa.String(20), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("stored_name", sa.String(80), nullable=False, unique=True),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assignment_files_assignment_id", "assignment_files", ["assignment_id"])
    op.create_index("ix_assignment_files_submission_id", "assignment_files", ["submission_id"])
    op.create_index("ix_assignment_files_stored_name", "assignment_files", ["stored_name"], unique=True)

    op.create_table(
        "study_materials",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(40), nullable=False),
        sa.Column("programme_id", sa.String(50)),
        sa.Column("level", sa.String(40)),
        sa.Column("material_type", sa.String(20), nullable=False, server_default="file"),
        sa.Column("stored_name", sa.String(80), unique=True),
        sa.Column("filename", sa.String(255)),
        sa.Column("content_type", sa.String(120)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("link_url", sa.String(500)),
        sa.Column("version", sa.String(20), server_default="1.0"),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_study_materials_category", "study_materials", ["category"])
    op.create_index("ix_study_materials_programme_id", "study_materials", ["programme_id"])

    op.create_table(
        "material_assignments",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("material_id", UUID, sa.ForeignKey("study_materials.id", ondelete="CASCADE"), nullable=False),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("assigned_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_material_assignments_material_id", "material_assignments", ["material_id"])
    op.create_index("ix_material_assignments_student_id", "material_assignments", ["student_id"])

    op.create_table(
        "resource_recommendations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("author_or_brand", sa.String(200)),
        sa.Column("description", sa.Text()),
        sa.Column("suitability", sa.String(120)),
        sa.Column("programme_id", sa.String(50)),
        sa.Column("image_url", sa.String(500)),
        sa.Column("external_url", sa.String(500)),
        sa.Column("faculty_note", sa.Text()),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_resource_recommendations_type", "resource_recommendations", ["resource_type"])
    op.create_index("ix_resource_recommendations_programme_id", "resource_recommendations", ["programme_id"])

    # ------------------------------------------------------------------
    # Syllabus / reports / exams
    # ------------------------------------------------------------------
    op.create_table(
        "syllabi",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("board", sa.String(80), nullable=False, server_default="academy"),
        sa.Column("programme_id", sa.String(50), nullable=False),
        sa.Column("grade", sa.String(40)),
        sa.Column("version", sa.String(40)),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_syllabi_programme_id", "syllabi", ["programme_id"])

    op.create_table(
        "syllabus_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("syllabus_id", UUID, sa.ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_item_id", UUID, sa.ForeignKey("syllabus_items.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("item_type", sa.String(30), server_default="topic"),
        sa.Column("learning_objective", sa.Text()),
        sa.Column("prerequisites", sa.Text()),
        sa.Column("practice_instructions", sa.Text()),
        sa.Column("faculty_notes", sa.Text()),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_syllabus_items_syllabus_id", "syllabus_items", ["syllabus_id"])

    op.create_table(
        "student_syllabus_progress",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("syllabus_id", UUID, sa.ForeignKey("syllabi.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", UUID, sa.ForeignKey("syllabus_items.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="not_started"),
        sa.Column("faculty_notes", sa.Text()),
        sa.Column("evidence", sa.Text()),
        sa.Column("date_introduced", sa.DateTime()),
        sa.Column("date_completed", sa.DateTime()),
        sa.Column("updated_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", "item_id", name="uq_progress_student_item"),
    )
    op.create_index("ix_student_syllabus_progress_enrollment_id", "student_syllabus_progress", ["enrollment_id"])
    op.create_index("ix_student_syllabus_progress_syllabus_id", "student_syllabus_progress", ["syllabus_id"])

    op.create_table(
        "monthly_reports",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("instructor_id", UUID, sa.ForeignKey("instructors.id", ondelete="SET NULL"), nullable=True),
        sa.Column("report_month", sa.String(7), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("previous_revision_id", UUID, sa.ForeignKey("monthly_reports.id", ondelete="SET NULL"), nullable=True),
        sa.Column("progress_summary", sa.Text()),
        sa.Column("topics_covered", sa.Text()),
        sa.Column("skills_demonstrated", sa.Text()),
        sa.Column("strengths", sa.Text()),
        sa.Column("areas_for_improvement", sa.Text()),
        sa.Column("practice_recommendations", sa.Text()),
        sa.Column("assignment_status", sa.Text()),
        sa.Column("syllabus_progress", sa.Text()),
        sa.Column("exam_preparation", sa.Text()),
        sa.Column("next_month_focus", sa.Text()),
        sa.Column("faculty_remarks", sa.Text()),
        sa.Column("staff_notes", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime()),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("enrollment_id", "report_month", "revision", name="uq_report_enrollment_month_revision"),
    )
    op.create_index("ix_monthly_reports_student_id", "monthly_reports", ["student_id"])
    op.create_index("ix_monthly_reports_enrollment_id", "monthly_reports", ["enrollment_id"])
    op.create_index("ix_monthly_reports_report_month", "monthly_reports", ["report_month"])
    op.create_index("ix_monthly_reports_status", "monthly_reports", ["status"])

    op.create_table(
        "exams",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("syllabus_id", UUID, sa.ForeignKey("syllabi.id", ondelete="SET NULL"), nullable=True),
        sa.Column("board", sa.String(80), nullable=False, server_default="academy"),
        sa.Column("instrument", sa.String(100), nullable=False),
        sa.Column("grade", sa.String(40)),
        sa.Column("pathway", sa.String(80)),
        sa.Column("application_status", sa.String(24), nullable=False, server_default="not_started"),
        sa.Column("payment_status", sa.String(24), server_default="not_applicable"),
        sa.Column("exam_window_start", sa.Date()),
        sa.Column("exam_window_end", sa.Date()),
        sa.Column("submission_deadline", sa.Date()),
        sa.Column("submission_status", sa.String(24), nullable=False, server_default="not_submitted"),
        sa.Column("submission_date", sa.DateTime()),
        sa.Column("submission_reference", sa.String(120)),
        sa.Column("readiness", sa.String(24), server_default="not_assessed"),
        sa.Column("result", sa.String(40)),
        sa.Column("certificate_reference", sa.String(120)),
        sa.Column("certificate_issued_at", sa.DateTime()),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exams_student_id", "exams", ["student_id"])
    op.create_index("ix_exams_enrollment_id", "exams", ["enrollment_id"])
    op.create_index("ix_exams_submission_deadline", "exams", ["submission_deadline"])

    op.create_table(
        "exam_items",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("exam_id", UUID, sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_type", sa.String(30), nullable=False, server_default="repertoire"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("details", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exam_items_exam_id", "exam_items", ["exam_id"])

    op.create_table(
        "milestones",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("student_id", UUID, sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enrollment_id", UUID, sa.ForeignKey("enrollments.id", ondelete="CASCADE"), nullable=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("milestone_type", sa.String(40), server_default="achievement"),
        sa.Column("due_date", sa.Date()),
        sa.Column("achieved_at", sa.DateTime()),
        sa.Column("status", sa.String(20), nullable=False, server_default="upcoming"),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_milestones_student_id", "milestones", ["student_id"])
    op.create_index("ix_milestones_due_date", "milestones", ["due_date"])


def downgrade() -> None:
    op.drop_table("milestones")
    op.drop_table("exam_items")
    op.drop_table("exams")
    op.drop_table("monthly_reports")
    op.drop_table("student_syllabus_progress")
    op.drop_table("syllabus_items")
    op.drop_table("syllabi")
    op.drop_table("resource_recommendations")
    op.drop_table("material_assignments")
    op.drop_table("study_materials")
    op.drop_table("assignment_files")
    op.drop_table("submissions")
    op.drop_table("assignments")
    op.drop_table("payment_events")
    op.drop_table("payment_allocations")
    op.drop_table("payments")
    op.drop_table("payment_orders")
    op.drop_table("invoices")
    op.drop_table("fee_packages")
    op.drop_table("session_status_history")
    op.drop_table("class_sessions")
    op.drop_table("notifications")
    op.drop_table("audit_events")
    op.drop_table("guardian_accounts")
    op.drop_index("ix_students_portal_slug", table_name="students")
    op.drop_column("students", "portal_slug")
