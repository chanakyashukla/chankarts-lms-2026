"""
Phase 7 — E2E regression tests for reports (Test D) and billing/family isolation (Test E).
"""
import datetime as dt
from decimal import Decimal

import pytest
import pytest_asyncio

from tests.test_phase5 import (  # noqa: F401 — re-used fixtures
    client,
    admin_user,
    instructor_user,
    student_user,
    enrollment,
    auth,
    _make_token,
)
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.models.user import User
from app.models.student import Student
from app.database import Base
from tests.test_phase5 import engine as phase5_engine, TestSessionLocal
from sqlalchemy import select


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    async with phase5_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with phase5_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ==================================================================
# Fixtures: second student + linked parent for isolation tests
# ==================================================================
@pytest_asyncio.fixture
async def student2_user():
    async with TestSessionLocal() as session:
        user = User(
            email="student5b@test.com",
            username="student5b",
            hashed_password=get_password_hash("StudentPass@123"),
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        from app.models.student import Student

        session.add(
            Student(
                user_id=user.id,
                cma_registration_id="CMA-2026-9002",
                portal_slug="test-student-5b",
                first_name="Diya",
                last_name="Patel",
                date_of_birth=dt.date(2011, 3, 2),
                status="active",
            )
        )
        await session.commit()
        return user


@pytest_asyncio.fixture
async def enrollment2(student2_user, instructor_user):
    from app.models.student import Student
    from app.models.instructor import Instructor
    from app.models.enrollment import Enrollment

    async with TestSessionLocal() as session:
        student = (await session.execute(select(Student).where(Student.user_id == student2_user.id))).scalar_one()
        instructor = (
            await session.execute(select(Instructor).where(Instructor.user_id == instructor_user.id))
        ).scalar_one()
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


@pytest_asyncio.fixture
async def parent_user_linked(admin_user, student_user):
    from app.models.student import Student
    from app.models.guardian import GuardianAccount

    async with TestSessionLocal() as session:
        user = User(
            email="parent_report@test.com",
            username="parent_report",
            hashed_password=get_password_hash("ParentPass@123"),
            role=UserRole.PARENT,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        student = (await session.execute(select(Student).where(Student.user_id == student_user.id))).scalar_one()
        session.add(GuardianAccount(user_id=user.id, student_id=student.id))
        await session.commit()
        return user


# ==================================================================
# Test D — Reports
# ==================================================================
@pytest.mark.asyncio
async def test_report_draft_hidden_from_student_and_parent(
    client, admin_user, student_user, parent_user_linked, enrollment
):
    student = (await TestSessionLocal().execute(select(Student).where(Student.user_id == student_user.id))).scalar_one()
    student_id = str(student.id)

    created = await client.post(
        "/api/v1/learning/reports",
        json={
            "student_id": student_id,
            "enrollment_id": str(enrollment.id),
            "report_month": "2026-10",
            "progress_summary": "Draft summary",
            "staff_notes": "INTERNAL ONLY",
        },
        headers=auth(admin_user),
    )
    assert created.status_code == 201, created.text

    # Student sees empty
    s_view = await client.get(f"/api/v1/learning/reports?student_id={student_id}", headers=auth(student_user))
    assert s_view.json() == []

    # Parent sees empty
    p_view = await client.get(f"/api/v1/learning/reports?student_id={student_id}", headers=auth(parent_user_linked))
    assert p_view.json() == []


@pytest.mark.asyncio
async def test_report_staff_notes_never_leak_to_student_parent(
    client, admin_user, instructor_user, student_user, parent_user_linked, enrollment
):
    student = (await TestSessionLocal().execute(select(Student).where(Student.user_id == student_user.id))).scalar_one()
    student_id = str(student.id)

    created = await client.post(
        "/api/v1/learning/reports",
        json={
            "student_id": student_id,
            "enrollment_id": str(enrollment.id),
            "report_month": "2026-10",
            "progress_summary": "Good month",
            "staff_notes": "SENSITIVE STAFF NOTE",
        },
        headers=auth(admin_user),
    )
    report_id = created.json()["id"]

    published = await client.post(
        f"/api/v1/learning/reports/{report_id}/publish", headers=auth(admin_user)
    )
    assert published.status_code == 200

    # Student view — no staff_notes key
    s_view = await client.get(f"/api/v1/learning/reports?student_id={student_id}", headers=auth(student_user))
    rows = s_view.json()
    assert len(rows) == 1
    assert "staff_notes" not in rows[0], "staff_notes leaked to student"

    # Parent view — no staff_notes key
    p_view = await client.get(
        f"/api/v1/learning/reports?student_id={student_id}", headers=auth(parent_user_linked)
    )
    rows = p_view.json()
    assert len(rows) == 1
    assert "staff_notes" not in rows[0], "staff_notes leaked to parent"

    # Instructor view — staff_notes present
    i_view = await client.get(f"/api/v1/learning/reports?student_id={student_id}", headers=auth(instructor_user))
    rows = i_view.json()
    assert rows[0].get("staff_notes") == "SENSITIVE STAFF NOTE"


@pytest.mark.asyncio
async def test_report_cross_user_403(
    client, admin_user, student_user, student2_user, parent_user_linked, enrollment, enrollment2
):
    student = (await TestSessionLocal().execute(select(Student).where(Student.user_id == student_user.id))).scalar_one()
    student2 = (
        await TestSessionLocal().execute(select(Student).where(Student.user_id == student2_user.id))
    ).scalar_one()
    sid, sid2 = str(student.id), str(student2.id)

    # Create published report for student 1
    created = await client.post(
        "/api/v1/learning/reports",
        json={"student_id": sid, "enrollment_id": str(enrollment.id), "report_month": "2026-10", "progress_summary": "x"},
        headers=auth(admin_user),
    )
    await client.post(f"/api/v1/learning/reports/{created.json()['id']}/publish", headers=auth(admin_user))

    # Unrelated student 2 tries to view student 1 report
    resp = await client.get(f"/api/v1/learning/reports?student_id={sid}", headers=auth(student2_user))
    assert resp.status_code == 403

    # Unrelated parent (linked to s1 only) tries to view student 2 report via student_id filter
    resp = await client.get(f"/api/v1/learning/reports?student_id={sid2}", headers=auth(parent_user_linked))
    assert resp.status_code == 403

    # Student tries to create a report
    resp = await client.post(
        "/api/v1/learning/reports",
        json={"student_id": sid, "enrollment_id": str(enrollment.id), "report_month": "2026-11"},
        headers=auth(student_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_report_parent_isolation_across_students(
    client, admin_user, student_user, student2_user, parent_user_linked, enrollment, enrollment2
):
    """Parent linked only to student1 must not see student2's published reports via list-all."""
    student = (await TestSessionLocal().execute(select(Student).where(Student.user_id == student_user.id))).scalar_one()
    student2 = (
        await TestSessionLocal().execute(select(Student).where(Student.user_id == student2_user.id))
    ).scalar_one()

    # Publish reports for both students
    for sid, eid in [(str(student.id), str(enrollment.id)), (str(student2.id), str(enrollment2.id))]:
        created = await client.post(
            "/api/v1/learning/reports",
            json={"student_id": sid, "enrollment_id": eid, "report_month": "2026-10", "progress_summary": "x"},
            headers=auth(admin_user),
        )
        await client.post(f"/api/v1/learning/reports/{created.json()['id']}/publish", headers=auth(admin_user))

    # Parent list-all — only sees linked student
    resp = await client.get("/api/v1/learning/reports", headers=auth(parent_user_linked))
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["student_id"] == str(student.id)


# ==================================================================
# Test E — Billing & family isolation
# ==================================================================
@pytest.mark.asyncio
async def test_fee_package_upsert_idempotent(client, admin_user):
    p1 = await client.post(
        "/api/v1/billing/packages",
        json={"code": "std_4", "name": "Std 4", "sessions_included": 4, "fee_paise": 450000, "session_duration_minutes": 60},
        headers=auth(admin_user),
    )
    assert p1.status_code == 201, p1.text
    pkg_id = p1.json()["id"]

    p2 = await client.post(
        "/api/v1/billing/packages",
        json={"code": "std_4", "name": "Std 4 v2", "sessions_included": 4, "fee_paise": 450000, "session_duration_minutes": 60},
        headers=auth(admin_user),
    )
    assert p2.status_code == 201
    assert p2.json()["id"] == pkg_id, "Upsert must reuse the same package id"
    assert p2.json()["name"] == "Std 4 v2"


@pytest.mark.asyncio
async def test_fee_package_invalid_code_422(client, admin_user):
    resp = await client.post(
        "/api/v1/billing/packages",
        json={"code": "Invalid-Code!", "name": "Bad", "sessions_included": 4, "fee_paise": 1, "session_duration_minutes": 60},
        headers=auth(admin_user),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_fee_package_non_admin_403(client, student_user):
    resp = await client.post(
        "/api/v1/billing/packages",
        json={"code": "hack", "name": "Hack", "sessions_included": 1, "fee_paise": 1, "session_duration_minutes": 60},
        headers=auth(student_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_invoice_scoping_student_parent(
    client, admin_user, student_user, student2_user, parent_user_linked, enrollment, enrollment2
):
    student = (await TestSessionLocal().execute(select(Student).where(Student.user_id == student_user.id))).scalar_one()
    student2 = (
        await TestSessionLocal().execute(select(Student).where(Student.user_id == student2_user.id))
    ).scalar_one()

    inv1 = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    assert inv1.status_code == 201, inv1.text
    inv2 = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment2.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    assert inv2.status_code == 201, inv2.text

    # Student 1 sees only own
    s1_view = await client.get("/api/v1/billing/invoices", headers=auth(student_user))
    assert len(s1_view.json()) == 1
    assert s1_view.json()[0]["student_id"] == str(student.id)

    # Parent sees only linked student (student 1)
    p_view = await client.get("/api/v1/billing/invoices", headers=auth(parent_user_linked))
    assert len(p_view.json()) == 1
    assert p_view.json()[0]["student_id"] == str(student.id)

    # Parent direct access to student 2 invoice → 403
    resp = await client.get(f"/api/v1/billing/invoices/{inv2.json()['id']}", headers=auth(parent_user_linked))
    assert resp.status_code == 403

    # Ledger scoping
    led = await client.get("/api/v1/billing/ledger", headers=auth(parent_user_linked))
    assert led.status_code == 200
    assert len(led.json()["entries"]) == 1
    assert led.json()["entries"][0]["student_id"] == str(student.id)


@pytest.mark.asyncio
async def test_family_payment_allocation_isolates_students(
    client, admin_user, student_user, student2_user, enrollment, enrollment2
):
    student = (await TestSessionLocal().execute(select(Student).where(Student.user_id == student_user.id))).scalar_one()
    student2 = (
        await TestSessionLocal().execute(select(Student).where(Student.user_id == student2_user.id))
    ).scalar_one()

    inv1 = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    inv2 = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment2.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    inv1_id, inv2_id = inv1.json()["id"], inv2.json()["id"]

    # Family payment allocated ONLY to inv1
    pay = await client.post(
        "/api/v1/billing/payments/manual",
        json={
            "amount_paise": 450000,
            "method": "upi",
            "allocations": [{"invoice_id": inv1_id, "amount_paise": 450000}],
        },
        headers=auth(admin_user),
    )
    assert pay.status_code == 201, pay.text

    # inv1 → paid
    i1 = await client.get(f"/api/v1/billing/invoices/{inv1_id}", headers=auth(admin_user))
    assert i1.json()["status"] == "paid"
    assert i1.json()["amount_paid_paise"] == 450000

    # inv2 → STILL pending (family isolation)
    i2 = await client.get(f"/api/v1/billing/invoices/{inv2_id}", headers=auth(admin_user))
    assert i2.json()["status"] == "pending", "Family payment isolation broken: unrelated invoice marked paid"
    assert i2.json()["amount_paid_paise"] == 0

    # Over-allocation on the same payment → 400
    over = await client.post(
        f"/api/v1/billing/payments/{pay.json()['id']}/allocations",
        json={"allocations": [{"invoice_id": inv2_id, "amount_paise": 450000}]},
        headers=auth(admin_user),
    )
    assert over.status_code == 400

    # Partial payment on inv2 → partially_paid
    pay2 = await client.post(
        "/api/v1/billing/payments/manual",
        json={"amount_paise": 200000, "method": "cash", "allocations": [{"invoice_id": inv2_id, "amount_paise": 200000}]},
        headers=auth(admin_user),
    )
    i2b = await client.get(f"/api/v1/billing/invoices/{inv2_id}", headers=auth(admin_user))
    assert i2b.json()["status"] == "partially_paid"
    assert i2b.json()["amount_paid_paise"] == 200000

    # Reverse the partial allocation → back to pending
    alloc_id = i2b.json()["allocations"][0]["id"]
    rev = await client.post(
        f"/api/v1/billing/allocations/{alloc_id}/reverse",
        json={"reason": "test reversal"},
        headers=auth(admin_user),
    )
    assert rev.status_code == 200, rev.text
    i2c = await client.get(f"/api/v1/billing/invoices/{inv2_id}", headers=auth(admin_user))
    assert i2c.json()["status"] == "pending"
    assert i2c.json()["amount_paid_paise"] == 0


@pytest.mark.asyncio
async def test_duplicate_invoice_409(client, admin_user, enrollment):
    inv = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    assert inv.status_code == 201
    dup = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_manual_payment_student_403(client, student_user, enrollment, admin_user):
    inv = await client.post(
        "/api/v1/billing/invoices",
        json={"enrollment_id": str(enrollment.id), "billing_month": "2026-10"},
        headers=auth(admin_user),
    )
    resp = await client.post(
        "/api/v1/billing/payments/manual",
        json={"amount_paise": 100, "method": "cash", "allocations": [{"invoice_id": inv.json()["id"], "amount_paise": 100}]},
        headers=auth(student_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_razorpay_webhook_invalid_signature_rejected(client):
    """Forged webhook must be rejected and must not poison the provider event id."""
    resp = await client.post(
        "/api/v1/billing/webhooks/razorpay",
        content=b'{"id":"evt_poison_test","event":"payment.captured","payload":{}}',
        headers={"X-Razorpay-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert b"Invalid signature" in resp.content

    # Repeat — still 400
    resp2 = await client.post(
        "/api/v1/billing/webhooks/razorpay",
        content=b'{"id":"evt_poison_test","event":"payment.captured","payload":{}}',
        headers={"X-Razorpay-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert resp2.status_code == 400

    # Ensure evt_poison_test was NOT recorded as a legitimate event
    from app.models.billing import PaymentEvent

    async with TestSessionLocal() as db:
        result = await db.execute(select(PaymentEvent).where(PaymentEvent.event_id == "evt_poison_test"))
        assert result.scalar_one_or_none() is None, "Forged webhook poisoned the provider event id"
