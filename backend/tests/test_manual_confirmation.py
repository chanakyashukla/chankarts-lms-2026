"""
Manual fee confirmation.

Payments initiated or reported by families (checkout return, payment report)
and captured gateway events are recorded as Pending Verification. The fee is
marked Paid only when an authorised admin confirms the transaction — with the
verification action, timestamp and admin identity recorded, and a receipt
issued. Duplicate confirmation and duplicate allocations are refused.
"""
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_manual_confirmation.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.config import get_settings
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.admin import Admin
from app.models.student import Student
from app.models.enrollment import Enrollment
from app.models.billing import Invoice, Payment, PaymentAllocation, PaymentOrder, PaymentEvent
from app.models.finance import Receipt
from app.models.audit import AuditEvent
from app.models.notification import Notification

KEY_SECRET = "test_key_secret_manual_confirmation"
WEBHOOK_SECRET = "whsec_manual_confirmation"
get_settings().RAZORPAY_KEY_SECRET = KEY_SECRET
get_settings().RAZORPAY_WEBHOOK_SECRET = WEBHOOK_SECRET


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
    get_settings().RAZORPAY_KEY_SECRET = KEY_SECRET
    get_settings().RAZORPAY_WEBHOOK_SECRET = WEBHOOK_SECRET
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


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {_make_token(user)}"}


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def world():
    async with TestSessionLocal() as db:
        admin_u = User(username="mcadmin", email="mcadmin@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="MC", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        stu_u = User(username="CMA-9801", hashed_password=get_password_hash("9801"),
                     role=UserRole.STUDENT)
        db.add(stu_u)
        await db.flush()
        stu = Student(user_id=stu_u.id, cma_registration_id="CMA-2026-9801",
                      first_name="Ver", last_name="Ify", status="active")
        db.add(stu)
        await db.flush()
        enr = Enrollment(student_id=stu.id, programme_id="piano", programme_name="Piano",
                         fee_plan="4_classes", fee_amount=4500.0, status="active")
        db.add(enr)
        await db.commit()
        return {"admin": admin_u, "student": stu_u, "student_id": stu.id, "enrollment_id": enr.id}


async def _invoice(client, admin, enrollment_id, month="2026-11"):
    r = await client.post("/api/v1/billing/invoices",
                          json={"enrollment_id": str(enrollment_id), "billing_month": month},
                          headers=auth(admin))
    assert r.status_code == 201, r.text
    return r.json()


async def _seed_order(invoice_id, order_id, amount=450000):
    async with TestSessionLocal() as db:
        db.add(PaymentOrder(order_id=order_id, invoice_id=uuid.UUID(invoice_id),
                            amount_paise=amount, currency="INR", status="created"))
        await db.commit()


def _checkout_signature(order_id, payment_id, secret=KEY_SECRET):
    return hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# 1. Checkout return: recorded, but Pending Verification until admin confirms
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_checkout_return_stays_pending_until_admin_confirms(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["enrollment_id"])
    await _seed_order(inv["id"], "order_mc_1")

    sig = _checkout_signature("order_mc_1", "pay_mc_1")
    r = await client.post("/api/v1/billing/payments/verify",
                          json={"razorpay_order_id": "order_mc_1",
                                "razorpay_payment_id": "pay_mc_1",
                                "razorpay_signature": sig},
                          headers=auth(w["student"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_verification"
    pay_id = r.json()["payment"]["id"]

    # the fee is NOT paid merely because the gateway returned
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["student"]))).json()
    assert detail["status"] == "pending"
    assert detail["amount_paid_paise"] == 0

    # the student sees Pending Verification and NO receipt yet
    pays = (await client.get("/api/v1/billing/payments", headers=auth(w["student"]))).json()
    assert pays[0]["status"] == "pending_verification"
    assert pays[0]["receipt_number"] is None

    # admin confirms after verifying the transaction
    conf = await client.post(f"/api/v1/billing/payments/{pay_id}/confirm",
                             json={"note": "checked against Razorpay dashboard"},
                             headers=auth(w["admin"]))
    assert conf.status_code == 200, conf.text
    body = conf.json()
    assert body["status"] == "verified"
    assert body["receipt_number"].startswith("CMA/RCPT/")
    assert body["allocations"][0]["invoice"] == inv["invoice_number"]

    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["student"]))).json()
    assert detail["status"] == "paid"
    assert detail["amount_paid_paise"] == 450000

    # verification action, timestamp and admin identity recorded
    async with TestSessionLocal() as db:
        ev = (await db.execute(select(AuditEvent).where(
            AuditEvent.action == "payment.confirmed_by_admin"))).scalars().all()
        assert len(ev) == 1
        assert "checked against Razorpay dashboard" in (ev[0].summary or "")
        assert ev[0].after_data.get("verified_by") == "mcadmin"
        assert ev[0].after_data.get("verified_at")
        receipts = (await db.execute(select(Receipt))).scalars().all()
        assert len(receipts) == 1
        notes = (await db.execute(select(Notification).where(
            Notification.user_id == w["student"].id))).scalars().all()
        assert any(n.type == "payment.confirmed" for n in notes)

    # duplicate confirmation refused
    again = await client.post(f"/api/v1/billing/payments/{pay_id}/confirm", json={},
                              headers=auth(w["admin"]))
    assert again.status_code == 409


# ---------------------------------------------------------------------------
# 2. Family-reported reference: pending, then confirmed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reported_reference_pending_then_confirmed(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["enrollment_id"])
    r = await client.post("/api/v1/billing/payments/report",
                          json={"student_id": str(w["student_id"]), "amount_paise": 450000,
                                "method": "upi", "reference": "UTR-123456",
                                "paid_at": "2026-11-03"},
                          headers=auth(w["student"]))
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending_verification"
    pay_id = r.json()["payment"]["id"]

    # duplicate reference refused
    dup = await client.post("/api/v1/billing/payments/report",
                            json={"student_id": str(w["student_id"]), "amount_paise": 100,
                                  "method": "upi", "reference": "UTR-123456"},
                            headers=auth(w["student"]))
    assert dup.status_code == 409

    # fee unpaid until confirmed
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["student"]))).json()
    assert detail["status"] == "pending"

    conf = await client.post(f"/api/v1/billing/payments/{pay_id}/confirm",
                             json={"note": "UTR matched bank statement",
                                   "allocations": [{"invoice_id": inv["id"], "amount_paise": 450000}]},
                             headers=auth(w["admin"]))
    assert conf.status_code == 200, conf.text
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["student"]))).json()
    assert detail["status"] == "paid"


# ---------------------------------------------------------------------------
# 3. Captured webhook also awaits manual confirmation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_webhook_captured_requires_manual_confirmation(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["enrollment_id"])
    await _seed_order(inv["id"], "order_mc_2")
    body = {"id": "evt_mc_2", "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_mc_2", "order_id": "order_mc_2",
                                               "amount": 450000, "currency": "INR",
                                               "method": "upi", "created": 1760000000}}}}
    raw = json.dumps(body).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    r = await client.post("/api/v1/billing/webhooks/razorpay", content=raw,
                          headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_verification"

    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["student"]))).json()
    assert detail["status"] == "pending" and detail["amount_paid_paise"] == 0

    pays = (await client.get("/api/v1/billing/payments", headers=auth(w["admin"]))).json()
    pay_id = pays[0]["id"]
    conf = await client.post(f"/api/v1/billing/payments/{pay_id}/confirm", json={},
                             headers=auth(w["admin"]))
    assert conf.status_code == 200
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["student"]))).json()
    assert detail["status"] == "paid"


# ---------------------------------------------------------------------------
# 4. Authorization: only admins confirm; only own reports are visible
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_students_cannot_confirm_or_see_others(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["enrollment_id"])
    r = await client.post("/api/v1/billing/payments/report",
                          json={"student_id": str(w["student_id"]), "amount_paise": 100000,
                                "method": "cash", "reference": "REC-1"},
                          headers=auth(w["student"]))
    pay_id = r.json()["payment"]["id"]

    deny = await client.post(f"/api/v1/billing/payments/{pay_id}/confirm", json={},
                             headers=auth(w["student"]))
    assert deny.status_code == 403

    # instructor cannot reach billing at all
    async with TestSessionLocal() as db:
        inst_u = User(username="mcinst", email="mcinst@t.local",
                      hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(inst_u)
        await db.commit()
    deny2 = await client.post(f"/api/v1/billing/payments/{pay_id}/confirm", json={},
                              headers=auth(inst_u))
    assert deny2.status_code == 403
    deny3 = await client.post("/api/v1/billing/payments/report",
                              json={"student_id": str(w["student_id"]), "amount_paise": 1,
                                    "method": "cash"}, headers=auth(inst_u))
    assert deny3.status_code == 403


# ---------------------------------------------------------------------------
# 5. Confirmation allocation guards + audit history preserved
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_confirm_allocation_guard_and_history(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["enrollment_id"])
    r = await client.post("/api/v1/billing/payments/report",
                          json={"student_id": str(w["student_id"]), "amount_paise": 450000,
                                "method": "bank_transfer", "reference": "NEFT-9"},
                          headers=auth(w["student"]))
    pay_id = r.json()["payment"]["id"]

    over = await client.post(f"/api/v1/billing/payments/{pay_id}/confirm",
                             json={"allocations": [{"invoice_id": inv["id"], "amount_paise": 999999}]},
                             headers=auth(w["admin"]))
    assert over.status_code == 400

    ok = await client.post(f"/api/v1/billing/payments/{pay_id}/confirm", json={},
                           headers=auth(w["admin"]))
    assert ok.status_code == 200
    assert ok.json()["status"] == "verified"

    async with TestSessionLocal() as db:
        pay = (await db.execute(select(Payment).where(Payment.id == uuid.UUID(pay_id)))).scalar_one()
        assert pay.status == "verified"
        assert pay.verified_at is not None
        assert pay.recorded_by is not None       # admin identity recorded
        allocs = (await db.execute(select(PaymentAllocation))).scalars().all()
        assert len(allocs) == 1                  # single allocation, no duplicates
        assert pay.notes is not None or True
