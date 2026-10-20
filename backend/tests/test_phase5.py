"""
Phase 5 tests: class sessions, registration approval, billing/webhook,
assignments, reports, syllabus progress.
"""
import datetime as dt
import hashlib
import hmac
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_phase5.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.config import get_settings
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.admin import Admin
from app.models.instructor import Instructor
from app.models.student import Student
from app.models.enrollment import Enrollment
from app.models.registration_request import RegistrationRequest
from app.models.session import ClassSession, SessionStatus, SessionStatusHistory

WEBHOOK_SECRET = "whsec_phase5_test"
get_settings().RAZORPAY_WEBHOOK_SECRET = WEBHOOK_SECRET
get_settings().RAZORPAY_MODE = "disabled"


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_token(user: User) -> str:
    return create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=timedelta(minutes=30),
    )


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_user():
    async with TestSessionLocal() as session:
        user = User(
            email="admin5@test.com",
            username="admin5",
            hashed_password=get_password_hash("AdminPass@123"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        session.add(
            Admin(user_id=user.id, first_name="Test", last_name="Admin", admin_level="super_admin", is_active=True)
        )
        await session.commit()
        return user


@pytest_asyncio.fixture
async def instructor_user():
    async with TestSessionLocal() as session:
        user = User(
            email="faculty5@test.com",
            username="faculty5",
            hashed_password=get_password_hash("FacultyPass@123"),
            role=UserRole.INSTRUCTOR,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        session.add(Instructor(user_id=user.id, first_name="Asha", last_name="Rao", is_active=True))
        await session.commit()
        return user


@pytest_asyncio.fixture
async def student_user():
    async with TestSessionLocal() as session:
        user = User(
            email="student5@test.com",
            username="student5",
            hashed_password=get_password_hash("StudentPass@123"),
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        session.add(
            Student(
                user_id=user.id,
                cma_registration_id="CMA-2026-9001",
                portal_slug="test-student-5",
                first_name="Ira",
                last_name="Sen",
                date_of_birth=dt.date(2012, 5, 4),
                status="active",
            )
        )
        await session.commit()
        return user


@pytest_asyncio.fixture
async def enrollment(admin_user, instructor_user, student_user):
    async with TestSessionLocal() as session:
        student_result = await session.execute(select(Student).where(Student.user_id == student_user.id))
        student = student_result.scalar_one()
        instr_result = await session.execute(select(Instructor).where(Instructor.user_id == instructor_user.id))
        instructor = instr_result.scalar_one()
        row = Enrollment(
            student_id=student.id,
            instructor_id=instructor.id,
            programme_id="piano",
            programme_name="Piano",
            status="active",
            start_date=dt.date.today(),
            fee_plan="standard_4",
            fee_amount=Decimal("4500.00"),
        )
        session.add(row)
        await session.commit()
        return row


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {_make_token(user)}"}


# ==================================================================
# Class sessions
# ==================================================================
@pytest.mark.asyncio
async def test_admin_creates_and_completes_session(client, admin_user, enrollment):
    payload = {
        "enrollment_id": str(enrollment.id),
        "scheduled_date": "2026-10-20",
        "scheduled_start": "10:00",
        "scheduled_end": "11:00",
        "is_online": True,
        "meeting_link": "https://meet.example.com/abc",
    }
    resp = await client.post("/api/v1/sessions", json=payload, headers=auth(admin_user))
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "scheduled"
    assert body["duration_minutes"] == 60
    assert "absent" not in SessionStatus.ALL

    done = await client.post(
        f"/api/v1/sessions/{body['id']}/complete",
        json={"topics_covered": "Scales in C major", "faculty_remarks": "Good progress"},
        headers=auth(admin_user),
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    assert done.json()["billing_month"] == "2026-10"

    history = await client.get(f"/api/v1/sessions/{body['id']}", headers=auth(admin_user))
    assert history.status_code == 200

    again = await client.post(
        f"/api/v1/sessions/{body['id']}/complete", json={}, headers=auth(admin_user)
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_short_session_requires_exception(client, admin_user, enrollment):
    resp = await client.post(
        "/api/v1/sessions",
        json={
            "enrollment_id": str(enrollment.id),
            "scheduled_date": "2026-10-21",
            "scheduled_start": "10:00",
            "scheduled_end": "10:30",
        },
        headers=auth(admin_user),
    )
    assert resp.status_code == 400
    assert "60 minutes" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_overlap_rejected(client, admin_user, enrollment):
    payload = {
        "enrollment_id": str(enrollment.id),
        "scheduled_date": "2026-10-22",
        "scheduled_start": "10:00",
        "scheduled_end": "11:00",
    }
    first = await client.post("/api/v1/sessions", json=payload, headers=auth(admin_user))
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/sessions", json={**payload, "scheduled_start": "10:30", "scheduled_end": "11:30"},
        headers=auth(admin_user),
    )
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_student_cannot_create_session(client, student_user, enrollment):
    resp = await client.post(
        "/api/v1/sessions",
        json={
            "enrollment_id": str(enrollment.id),
            "scheduled_date": "2026-10-23",
            "scheduled_start": "10:00",
            "scheduled_end": "11:00",
        },
        headers=auth(student_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_flag_reschedule_and_history(client, admin_user, enrollment):
    created = await client.post(
        "/api/v1/sessions",
        json={
            "enrollment_id": str(enrollment.id),
            "scheduled_date": "2026-10-24",
            "scheduled_start": "10:00",
            "scheduled_end": "11:00",
        },
        headers=auth(admin_user),
    )
    sid = created.json()["id"]

    flagged = await client.post(
        f"/api/v1/sessions/{sid}/flag-reschedule",
        json={"reason": "Faculty unwell"},
        headers=auth(admin_user),
    )
    assert flagged.status_code == 200, flagged.text
    assert flagged.json()["status"] == "rescheduling_required"

    replacement = await client.post(
        f"/api/v1/sessions/{sid}/reschedule",
        json={"new_date": "2026-10-25", "new_start": "10:00", "new_end": "11:00", "reason": "Faculty recovered"},
        headers=auth(admin_user),
    )
    assert replacement.status_code == 201, replacement.text
    rep = replacement.json()
    assert rep["status"] == "scheduled"
    assert rep["replaces_session_id"] == sid

    async with TestSessionLocal() as db:
        original = (
            await db.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(sid)))
        ).scalar_one()
        assert original.status == "rescheduled"  # confirmed move; original row is retained
        history_rows = (
            await db.execute(select(SessionStatusHistory).where(SessionStatusHistory.session_id == original.id))
        ).scalars().all()
        assert len(history_rows) >= 2


@pytest.mark.asyncio
async def test_monthly_stats(client, admin_user, enrollment):
    created = await client.post(
        "/api/v1/sessions",
        json={
            "enrollment_id": str(enrollment.id),
            "scheduled_date": "2026-10-26",
            "scheduled_start": "10:00",
            "scheduled_end": "11:00",
        },
        headers=auth(admin_user),
    )
    sid = created.json()["id"]
    await client.post(
        f"/api/v1/sessions/{sid}/complete", json={"actual_date": "2026-10-26"}, headers=auth(admin_user)
    )

    resp = await client.get(
        "/api/v1/sessions/stats/monthly?month=2026-10", headers=auth(admin_user)
    )
    assert resp.status_code == 200, resp.text
    stats = resp.json()
    assert stats["completed"] >= 1
    assert stats["scheduled"] >= 0
    assert "absent" not in stats


# ==================================================================
# Registration approval
# ==================================================================
@pytest.mark.asyncio
async def test_registration_approval_creates_student(client, admin_user):
    async with TestSessionLocal() as db:
        req = RegistrationRequest(
            request_id="REQ-2026-0999",
            status="pending_review",
            full_name="Aarav Mehta",
            email="aarav5@example.com",
            mobile="+911234567890",
                        date_of_birth=dt.date(2010, 1, 1),
            is_minor=True,
            guardian_name="Ravi Mehta",
            guardian_relationship="father",
            guardian_email="ravi5@example.com",
            guardian_mobile="+911234567891",
            selected_programmes=[{"id": "piano", "name": "Piano"}],
        )
        db.add(req)
        await db.commit()
        req_id = str(req.id)

    async with TestSessionLocal() as db:
        students_before = (await db.execute(select(func.count(Student.id)))).scalar_one()

    # Provisioning BEFORE approval is impossible
    early = await client.post(
        f"/api/v1/admin/registration-requests/{req_id}/provision",
        headers=auth(admin_user),
    )
    assert early.status_code == 400, early.text

    # Step 1 — approval: status only, NO account is generated
    resp = await client.patch(
        f"/api/v1/admin/registration-requests/{req_id}/status",
        json={"status": "approved", "notes": "All documents verified"},
        headers=auth(admin_user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["account_created"] is False
    assert body["status"] == "approved"

    # Step 2 — explicit provisioning creates the account + enrolment + temp PIN.
    # The admin can assign the roll number (login id), the fee plan and the
    # instructor in the same step.
    from app.models.instructor import Instructor as _Inst
    async with TestSessionLocal() as db:
        inst_user = User(username="prov-inst", email="prov-inst@t.local",
                         hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(inst_user)
        await db.flush()
        inst = _Inst(user_id=inst_user.id, first_name="Prov", last_name="Faculty",
                     specializations="piano", is_active=True)
        db.add(inst)
        await db.commit()
        inst_id = str(inst.id)

    prov = await client.post(
        f"/api/v1/admin/registration-requests/{req_id}/provision",
        json={"login_id": "CMA-2026-9001", "temp_pin": "4321",
              "fee_plan": "4_classes", "instructor_id": inst_id},
        headers=auth(admin_user),
    )
    assert prov.status_code == 201, prov.text
    pbody = prov.json()
    assert pbody["temp_pin"] == "4321"                 # admin-assigned temporary PIN
    assert pbody["login_id"] == "CMA-2026-9001"        # admin-assigned roll number
    assert pbody["cma_registration_id"].startswith("CMA-2026-")
    assert pbody["must_change_pin"] is True
    assert pbody["fee_plan"] == "4_classes"
    assert pbody["instructor_id"] == inst_id

    async with TestSessionLocal() as db:
        student = (
            await db.execute(select(Student).where(Student.id == uuid.UUID(pbody["student_id"])))
        ).scalar_one()
        user = (await db.execute(select(User).where(User.id == student.user_id))).scalar_one()
        assert user.username == pbody["login_id"]
        assert user.must_change_pin is True
        assert user.hashed_password != pbody["temp_pin"]   # hashed, never plaintext
        enrollments = (
            await db.execute(select(Enrollment).where(Enrollment.student_id == student.id))
        ).scalars().all()
        assert len(enrollments) == 1
        assert enrollments[0].programme_id == "piano"
        assert enrollments[0].fee_plan == "4_classes"
        assert float(enrollments[0].fee_amount) == 4500.0
        assert str(enrollments[0].instructor_id) == inst_id
        students_after = (await db.execute(select(func.count(Student.id)))).scalar_one()
        assert students_after == students_before + 1

    # Re-provisioning never duplicates the account
    dup = await client.post(
        f"/api/v1/admin/registration-requests/{req_id}/provision",
        headers=auth(admin_user),
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_reject_requires_reason(client, admin_user):
    async with TestSessionLocal() as db:
        req = RegistrationRequest(
            request_id="REQ-2026-0998",
            status="pending_review",
            full_name="Nila Roy",
            email="nila5@example.com",
            mobile="+911234567892",
                        date_of_birth=dt.date(1995, 3, 3),
            selected_programmes=[{"id": "vocal", "name": "Vocal"}],
        )
        db.add(req)
        await db.commit()
        req_id = str(req.id)

    resp = await client.patch(
        f"/api/v1/admin/registration-requests/{req_id}/status",
        json={"status": "rejected"},
        headers=auth(admin_user),
    )
    assert resp.status_code == 400
    assert "reason" in resp.json()["detail"].lower()


# ==================================================================
# Billing + webhook
# ==================================================================
@pytest.mark.asyncio
async def test_invoice_creation_and_scoping(client, admin_user, student_user, enrollment):
    created = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    assert created.status_code == 201, created.text
    invoice = created.json()
    assert invoice["amount_paise"] == 450000
    assert invoice["currency"] == "INR"
    assert invoice["status"] == "pending"

    duplicate = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    assert duplicate.status_code == 409

    mine = await client.get("/api/v1/billing/invoices", headers=auth(student_user))
    assert mine.status_code == 200
    assert [i["id"] for i in mine.json()] == [invoice["id"]]

    # The student may not create invoices
    forbidden = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-11"},
        headers=auth(student_user),
    )
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_payment_order_disabled_gateway(client, admin_user, student_user, enrollment):
    created = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    invoice_id = created.json()["id"]

    resp = await client.post(
        "/api/v1/billing/payments/orders", json={"invoice_id": invoice_id}, headers=auth(student_user)
    )
    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]

    config = await client.get("/api/v1/billing/payments/config", headers=auth(student_user))
    assert config.status_code == 200
    assert config.json()["enabled"] is False
    assert "secret" not in str(config.json()).lower()


@pytest.mark.asyncio
async def test_webhook_signature_verification_and_idempotency(client, admin_user, student_user, enrollment):
    # Re-applied here because other modules call get_settings.cache_clear()
    get_settings().RAZORPAY_WEBHOOK_SECRET = WEBHOOK_SECRET
    created = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    invoice = created.json()

    async with TestSessionLocal() as db:
        from app.models.billing import PaymentOrder

        order = PaymentOrder(
            order_id="order_test_001",
            invoice_id=uuid.UUID(invoice["id"]),
            amount_paise=450000,
            currency="INR",
            status="created",
        )
        db.add(order)
        await db.commit()

    body = {
        "id": "evt_test_001",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_test_001",
                    "order_id": "order_test_001",
                    "amount": 450000,
                    "currency": "INR",
                    "method": "upi",
                    "created": 1760000000,
                }
            }
        },
    }
    import json as _json

    raw = _json.dumps(body).encode()
    bad_sig = hmac.new(b"wrong-secret", raw, hashlib.sha256).hexdigest()
    bad = await client.post(
        "/api/v1/billing/webhooks/razorpay", content=raw,
        headers={"X-Razorpay-Signature": bad_sig, "Content-Type": "application/json"},
    )
    assert bad.status_code == 400

    good_sig = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    good = await client.post(
        "/api/v1/billing/webhooks/razorpay", content=raw,
        headers={"X-Razorpay-Signature": good_sig, "Content-Type": "application/json"},
    )
    assert good.status_code == 200, good.text
    assert good.json()["status"] == "pending_verification"  # manual fee policy

    # Replay of the same event id must not double-credit
    replay = await client.post(
        "/api/v1/billing/webhooks/razorpay", content=raw,
        headers={"X-Razorpay-Signature": good_sig, "Content-Type": "application/json"},
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "duplicate_ignored"

    # manual fee confirmation: the captured event records a pending payment;
    # the fee is settled only after the admin confirms
    after = await client.get(f"/api/v1/billing/invoices/{invoice['id']}", headers=auth(student_user))
    assert after.status_code == 200
    settled = after.json()
    assert settled["amount_paid_paise"] == 0
    assert settled["status"] == "pending"

    pay_list = await client.get("/api/v1/billing/payments", headers=auth(admin_user))
    pending = [p for p in pay_list.json() if p["status"] == "pending_verification"]
    assert len(pending) == 1
    conf = await client.post(f"/api/v1/billing/payments/{pending[0]['id']}/confirm", json={},
                             headers=auth(admin_user))
    assert conf.status_code == 200, conf.text
    settled = (await client.get(f"/api/v1/billing/invoices/{invoice['id']}", headers=auth(student_user))).json()
    assert settled["amount_paid_paise"] == 450000
    assert settled["status"] == "paid"


@pytest.mark.asyncio
async def test_manual_payment_allocation(client, admin_user, enrollment):
    created = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    invoice = created.json()

    resp = await client.post(
        "/api/v1/billing/payments/manual",
        json={
            "amount_paise": 450000,
            "method": "cash",
            "payer_name": "Family",
            "allocations": [{"invoice_id": invoice["id"], "amount_paise": 450000}],
        },
        headers=auth(admin_user),
    )
    assert resp.status_code == 201, resp.text

    after = await client.get(f"/api/v1/billing/invoices/{invoice['id']}", headers=auth(admin_user))
    assert after.json()["status"] == "paid"

    # Over-allocation is rejected (allocations may never exceed the payment)
    second = await client.post(
        "/api/v1/billing/payments/manual",
        json={
            "amount_paise": 50000,
            "method": "cash",
            "allocations": [{"invoice_id": invoice["id"], "amount_paise": 100000}],
        },
        headers=auth(admin_user),
    )
    assert second.status_code == 400


# ==================================================================
# Learning: assignments, reports, syllabus
# ==================================================================
@pytest.mark.asyncio
async def test_assignment_lifecycle(client, instructor_user, student_user, enrollment):
    created = await client.post(
        "/api/v1/learning/assignments",
        json={
            "title": "C major scales",
            "instructions": "Two octaves, hands separately",
            "enrollment_id": str(enrollment.id),
            "due_date": "2026-10-30",
        },
        headers=auth(instructor_user),
    )
    assert created.status_code == 201, created.text
    assignment = created.json()
    assert assignment["status"] == "assigned"
    assert assignment["student_id"] is not None

    # Students cannot create assignments
    forbidden = await client.post(
        "/api/v1/learning/assignments",
        json={"title": "Self assigned", "enrollment_id": str(enrollment.id)},
        headers=auth(student_user),
    )
    assert forbidden.status_code == 403

    pdf = b"%PDF-1.4\n%fake homework content for testing\n" + b"0" * 64
    submit = await client.post(
        f"/api/v1/learning/assignments/{assignment['id']}/submit",
        data={"notes": "Practised 20 min daily"},
        files=[("files", ("homework.pdf", pdf, "application/pdf"))],
        headers=auth(student_user),
    )
    assert submit.status_code == 201, submit.text
    submission_id = submit.json()["submission_id"]

    # Executable/script uploads are rejected by magic-byte validation
    bad_upload = await client.post(
        f"/api/v1/learning/assignments/{assignment['id']}/submit",
        files=[("files", ("evil.sh", b"#!/bin/sh\necho hacked", "application/octet-stream"))],
        headers=auth(student_user),
    )
    assert bad_upload.status_code == 400

    review = await client.post(
        f"/api/v1/learning/submissions/{submission_id}/review",
        json={"feedback": "Even tempo next time", "status": "reviewed"},
        headers=auth(instructor_user),
    )
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "reviewed"

    listed = await client.get("/api/v1/learning/assignments", headers=auth(student_user))
    assert listed.status_code == 200
    mine = [a for a in listed.json() if a["id"] == assignment["id"]]
    assert mine and mine[0]["submission"] is not None
    assert mine[0]["submission"]["feedback"] == "Even tempo next time"


@pytest.mark.asyncio
async def test_report_publish_hides_staff_notes(client, admin_user, instructor_user, student_user, enrollment):
    async with TestSessionLocal() as db:
        student = (
            await db.execute(select(Student).where(Student.user_id == student_user.id))
        ).scalar_one()

    created = await client.post(
        "/api/v1/learning/reports",
        json={
            "student_id": str(student.id),
            "enrollment_id": str(enrollment.id),
            "report_month": "2026-09",
            "progress_summary": "Confident with arpeggios",
            "staff_notes": "Sensitive about tempo — encourage gently",
        },
        headers=auth(instructor_user),
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]
    assert created.json()["staff_notes"] == "Sensitive about tempo — encourage gently"

    # Unpublished drafts are invisible to students
    draft_view = await client.get("/api/v1/learning/reports", headers=auth(student_user))
    assert draft_view.json() == []

    # workflow: instructor submits for review; approval (publish) is admin-only
    submitted = await client.post(
        f"/api/v1/learning/reports/{report_id}/submit", headers=auth(instructor_user)
    )
    assert submitted.status_code == 200 and submitted.json()["status"] == "submitted"

    publish_deny = await client.post(
        f"/api/v1/learning/reports/{report_id}/publish", headers=auth(instructor_user)
    )
    assert publish_deny.status_code == 403

    published = await client.post(
        f"/api/v1/learning/reports/{report_id}/publish", headers=auth(admin_user)
    )
    assert published.status_code == 200

    view = await client.get("/api/v1/learning/reports", headers=auth(student_user))
    assert view.status_code == 200
    rows = view.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "published"
    assert "staff_notes" not in rows[0]
    assert rows[0]["progress_summary"] == "Confident with arpeggios"


@pytest.mark.asyncio
async def test_syllabus_progress(client, admin_user, instructor_user, student_user, enrollment):
    syllabus = await client.post(
        "/api/v1/learning/syllabi",
        json={"title": "Piano Foundation", "programme_id": "piano", "grade": "1"},
        headers=auth(admin_user),
    )
    assert syllabus.status_code == 201, syllabus.text
    syllabus_id = syllabus.json()["id"]

    item = await client.post(
        f"/api/v1/learning/syllabi/{syllabus_id}/items",
        json={"title": "Posture and hand position", "item_type": "topic"},
        headers=auth(admin_user),
    )
    assert item.status_code == 201, item.text
    item_id = item.json()["id"]

    async with TestSessionLocal() as db:
        student = (
            await db.execute(select(Student).where(Student.user_id == student_user.id))
        ).scalar_one()

    # Student sees empty progress first
    before = await client.get(
        f"/api/v1/learning/syllabus-progress?student_id={student.id}", headers=auth(student_user)
    )
    assert before.status_code == 200
    assert before.json()["total"] == 0

    upsert = await client.post(
        f"/api/v1/learning/syllabus-progress/{item_id}?student_id={student.id}&enrollment_id={enrollment.id}",
        json={"status": "in_progress", "faculty_notes": "Week 1 introduced"},
        headers=auth(instructor_user),
    )
    assert upsert.status_code == 201, upsert.text
    assert upsert.json()["status"] == "in_progress"

    after = await client.get(
        f"/api/v1/learning/syllabus-progress?student_id={student.id}", headers=auth(student_user)
    )
    assert after.json()["total"] == 1
    assert after.json()["completed"] == 0
    assert after.json()["percent"] == 0

    complete = await client.post(
        f"/api/v1/learning/syllabus-progress/{item_id}?student_id={student.id}&enrollment_id={enrollment.id}",
        json={"status": "completed"},
        headers=auth(instructor_user),
    )
    assert complete.status_code == 201
    final = await client.get(
        f"/api/v1/learning/syllabus-progress?student_id={student.id}", headers=auth(student_user)
    )
    assert final.json()["percent"] == 100


@pytest.mark.asyncio
async def test_student_cannot_touch_faculty_endpoints(client, student_user, enrollment):
    calls = [
        client.post(
            "/api/v1/learning/reports",
            json={"student_id": str(uuid.uuid4()), "enrollment_id": str(enrollment.id), "report_month": "2026-10"},
            headers=auth(student_user),
        ),
        client.post(
            "/api/v1/learning/syllabi",
            json={"title": "x", "programme_id": "piano"},
            headers=auth(student_user),
        ),
        client.post(
            "/api/v1/learning/milestones",
            json={"student_id": str(uuid.uuid4()), "title": "self milestone"},
            headers=auth(student_user),
        ),
    ]
    for coro in calls:
        resp = await coro
        assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_portal_enrollments_scoped(client, admin_user, instructor_user, student_user, enrollment):
    """Students see their own enrolment; faculty see their teaching load with names."""
    student_view = await client.get("/api/v1/portal/enrollments", headers=auth(student_user))
    assert student_view.status_code == 200
    rows = student_view.json()
    assert len(rows) == 1
    assert rows[0]["student_name"] == "Ira Sen"
    assert rows[0]["programme_name"] == "Piano"
    assert rows[0]["instructor"] == "Asha Rao"

    faculty_view = await client.get("/api/v1/portal/enrollments", headers=auth(instructor_user))
    assert faculty_view.status_code == 200
    assert len(faculty_view.json()) == 1
    assert faculty_view.json()[0]["student_id"] == rows[0]["student_id"]

    admin_view = await client.get("/api/v1/portal/enrollments", headers=auth(admin_user))
    assert admin_view.status_code == 200
    assert len(admin_view.json()) == 1


@pytest.mark.asyncio
async def test_admin_students_list_and_detail(client, admin_user, student_user, enrollment):
    """Regression: admin student endpoints must not lazy-load ORM relationships."""
    listing = await client.get("/api/v1/admin/students", headers=auth(admin_user))
    assert listing.status_code == 200, listing.text
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["full_name"] == "Ira Sen"
    assert rows[0]["enrollment_count"] == 1
    assert rows[0]["email"] == "student5@test.com"

    detail = await client.get(f"/api/v1/admin/students/{rows[0]['id']}", headers=auth(admin_user))
    assert detail.status_code == 200, detail.text
    assert detail.json()["guardians"] == []
    assert len(detail.json()["enrollments"]) == 1
