"""
Fee ledger, flexible payments and reconciliation.

Covers the required verification scenarios:
 1. full cash payment   2. partial cash + instalment   3. UPI with reference
 4. advance applied to a future month   5. one payment settles two charges
 6. exam fee paid by academy, reimbursed later   7. verified online webhook
 8. invalid webhook signature rejected   9. duplicate webhook idempotent
10. failed/pending online events do not mark paid   11. family ledger isolation
12. instructors blocked from financial controls   13. idempotent charge generation
14. payment reversal with audit + correct balance
"""
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_fee_ledger.db"
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
from app.models.guardian import GuardianAccount
from app.models.enrollment import Enrollment
from app.models.billing import Invoice, Payment, PaymentAllocation, PaymentOrder
from app.models.finance import CreditLedgerEntry, ExamFee, Receipt
from app.models.audit import AuditEvent

WEBHOOK_SECRET = "whsec_fee_ledger_test"
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
    """admin, instructor, family A (student A1 + parent A), family B (student B1 + parent B)."""
    async with TestSessionLocal() as db:
        admin_u = User(username="fladmin", email="fladmin@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="FL", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        inst_u = User(username="flinst", email="flinst@t.local",
                      hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(inst_u)
        await db.flush()
        inst = Instructor(user_id=inst_u.id, first_name="FL", last_name="Faculty",
                          specializations="piano", is_active=True)
        db.add(inst)

        def mk_student(username, first):
            u = User(username=username, hashed_password=get_password_hash(username),
                     role=UserRole.STUDENT)
            db.add(u)
            return u, first

        a1_u, _ = mk_student("CMA-9701", "Al")
        b1_u, _ = mk_student("CMA-9702", "Be")
        pa_u = User(username="flparenta", email="flparenta@t.local",
                    hashed_password=get_password_hash("x"), role=UserRole.PARENT)
        pb_u = User(username="flparentb", email="flparentb@t.local",
                    hashed_password=get_password_hash("x"), role=UserRole.PARENT)
        db.add_all([pa_u, pb_u])
        await db.flush()
        a1 = Student(user_id=a1_u.id, cma_registration_id="CMA-2026-9701",
                     first_name="Al", last_name="Pha", status="active")
        b1 = Student(user_id=b1_u.id, cma_registration_id="CMA-2026-9702",
                     first_name="Be", last_name="Ta", status="active")
        db.add_all([a1, b1])
        await db.flush()
        db.add(GuardianAccount(user_id=pa_u.id, student_id=a1.id, relationship="mother"))
        db.add(GuardianAccount(user_id=pb_u.id, student_id=b1.id, relationship="father"))

        e_a = Enrollment(student_id=a1.id, programme_id="piano", programme_name="Piano",
                         instructor_id=inst.id, fee_plan="4_classes", fee_amount=4500.0,
                         status="active")
        e_b = Enrollment(student_id=b1.id, programme_id="guitar", programme_name="Guitar",
                         instructor_id=inst.id, fee_plan="8_classes", fee_amount=8000.0,
                         status="active")
        db.add_all([e_a, e_b])
        await db.commit()
        return {"admin": admin_u, "instructor": inst_u,
                "a1": a1_u, "a1_id": a1.id, "pa": pa_u,
                "b1": b1_u, "b1_id": b1.id, "pb": pb_u,
                "e_a": e_a.id, "e_b": e_b.id}


async def _invoice(client, admin, enrollment_id, month="2026-11", **extra):
    r = await client.post("/api/v1/billing/invoices",
                          json={"enrollment_id": str(enrollment_id), "billing_month": month, **extra},
                          headers=auth(admin))
    assert r.status_code == 201, r.text
    return r.json()


async def _manual_payment(client, admin, amount, allocations, method="cash", **extra):
    r = await client.post("/api/v1/billing/payments/manual",
                          json={"amount_paise": amount, "method": method,
                                "allocations": allocations, **extra},
                          headers=auth(admin))
    return r


# ---------------------------------------------------------------------------
# 1. Full cash payment
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_cash_payment_recorded_by_admin(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    r = await _manual_payment(client, w["admin"], 450000,
                              [{"invoice_id": inv["id"], "amount_paise": 450000}],
                              reference="CASH-001", payer_name="Al's mother")
    assert r.status_code == 201, r.text
    pay = r.json()
    assert pay["status"] == "verified"
    assert pay["source"] == "manual"
    assert pay["receipt_number"].startswith("CMA/RCPT/")

    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert detail["status"] == "paid"
    assert detail["outstanding_paise"] == 0

    # receipt is generated and stored exactly once
    async with TestSessionLocal() as db:
        receipts = (await db.execute(select(Receipt))).scalars().all()
        assert len(receipts) == 1
    receipt = await client.get(f"/api/v1/billing/payments/{pay['id']}/receipt", headers=auth(w["admin"]))
    assert receipt.status_code == 200
    assert pay["receipt_number"] in receipt.text


# ---------------------------------------------------------------------------
# 2. Partial payment then second instalment
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_partial_cash_then_second_instalment(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    r1 = await _manual_payment(client, w["admin"], 200000,
                               [{"invoice_id": inv["id"], "amount_paise": 200000}])
    assert r1.status_code == 201
    mid = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert mid["status"] == "partially_paid"
    assert mid["outstanding_paise"] == 250000

    r2 = await _manual_payment(client, w["admin"], 250000,
                               [{"invoice_id": inv["id"], "amount_paise": 250000}])
    assert r2.status_code == 201
    final = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert final["status"] == "paid"
    assert final["amount_paid_paise"] == 450000

    # never "paid" on partial alone — asserted above at the mid point
    history = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert len(history.get("allocations", [])) == 2


# ---------------------------------------------------------------------------
# 3. UPI payment with reference
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_upi_payment_with_reference(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_b"])
    r = await _manual_payment(client, w["admin"], 800000,
                              [{"invoice_id": inv["id"], "amount_paise": 800000}],
                              method="upi", reference="UPI-FL-2026-0001")
    assert r.status_code == 201
    assert r.json()["method"] == "upi"
    assert r.json()["provider_payment_id"] == "UPI-FL-2026-0001"
    # clearly labelled as admin-recorded
    audits = (await db_audits("payment.manual_recorded"))
    assert any("not an independently verified bank transaction" in (a.summary or "") for a in audits)


async def db_audits(action):
    async with TestSessionLocal() as db:
        return (await db.execute(select(AuditEvent).where(AuditEvent.action == action))).scalars().all()


# ---------------------------------------------------------------------------
# 4. Advance payment applied to a future month
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_advance_payment_applied_to_future_month(client, world):
    w = world
    # advance of ₹3,000 kept on the account
    adv = await client.post("/api/v1/billing/credits/advance",
                            json={"student_id": str(w["a1_id"]), "amount_paise": 300000,
                                  "method": "upi", "reference": "ADV-1",
                                  "payer_name": "Al's mother"},
                            headers=auth(w["admin"]))
    assert adv.status_code == 201, adv.text
    assert adv.json()["balance_paise"] == 300000

    # future charge created
    inv = await _invoice(client, w["admin"], w["e_a"], month="2026-12")
    applied = await client.post("/api/v1/billing/credits/apply",
                                json={"student_id": str(w["a1_id"]), "invoice_id": inv["id"],
                                      "amount_paise": 300000, "note": "Dec tuition"},
                                headers=auth(w["admin"]))
    assert applied.status_code == 200, applied.text
    assert applied.json()["balance_paise"] == 0
    assert applied.json()["invoice"]["amount_paid_paise"] == 300000
    assert applied.json()["invoice"]["status"] == "partially_paid"

    # ledger shows the credit trail
    credits = (await client.get(f"/api/v1/billing/credits?student_id={w['a1_id']}",
                                headers=auth(w["admin"]))).json()
    kinds = sorted(c["kind"] for c in credits["entries"])
    assert kinds == ["advance", "applied"]
    assert credits["balance_paise"] == 0


# ---------------------------------------------------------------------------
# 5. One payment settles two charges (family split)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_one_payment_settles_two_charges(client, world):
    w = world
    inv1 = await _invoice(client, w["admin"], w["e_a"], month="2026-11")
    inv2 = await _invoice(client, w["admin"], w["e_b"], month="2026-11")
    r = await _manual_payment(client, w["admin"], 1250000,
                              [{"invoice_id": inv1["id"], "amount_paise": 450000},
                               {"invoice_id": inv2["id"], "amount_paise": 800000}],
                              payer_name="Family payment")
    assert r.status_code == 201, r.text
    d1 = (await client.get(f"/api/v1/billing/invoices/{inv1['id']}", headers=auth(w["admin"]))).json()
    d2 = (await client.get(f"/api/v1/billing/invoices/{inv2['id']}", headers=auth(w["admin"]))).json()
    assert d1["status"] == "paid" and d2["status"] == "paid"

    # over-allocation is refused
    inv3 = await _invoice(client, w["admin"], w["e_a"], month="2027-01")
    over = await client.post(f"/api/v1/billing/payments/{r.json()['id']}/allocations",
                             json={"allocations": [{"invoice_id": inv3["id"], "amount_paise": 1}]},
                             headers=auth(w["admin"]))
    assert over.status_code == 400


# ---------------------------------------------------------------------------
# 6. Exam fee: academy pays provider, family reimburses later
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exam_fee_academy_paid_then_reimbursed(client, world):
    w = world
    created = await client.post("/api/v1/billing/exam-fees",
                                json={"student_id": str(w["a1_id"]), "board": "Trinity",
                                      "instrument": "piano", "grade_level": "Grade 2",
                                      "exam_session": "Spring 2027",
                                      "fee_charged_paise": 600000,
                                      "academy_paid_paise": 600000,
                                      "provider_reference": "TRIN-7788",
                                      "billing_month": "2026-11"},
                                headers=auth(w["admin"]))
    assert created.status_code == 201, created.text
    exam = created.json()
    assert exam["status"] == "academy_paid"
    assert exam["reimbursement_balance_paise"] == 600000
    # the family charge exists as a SEPARATE exam invoice
    assert exam["invoice"]["charge_type"] == "exam"
    assert exam["invoice"]["amount_paise"] == 600000

    # academy payment to the board is NOT money received — no tuition payment exists
    pays = (await client.get("/api/v1/billing/payments", headers=auth(w["admin"]))).json()
    assert pays == [] or all(p["amount_paise"] != 600000 for p in pays)

    reimb = await client.post(f"/api/v1/billing/exam-fees/{exam['id']}/reimburse",
                              json={"amount_paise": 300000, "method": "upi",
                                    "date": "2026-11-20", "reference": "RIMB-1"},
                              headers=auth(w["admin"]))
    assert reimb.status_code == 200, reimb.text
    body = reimb.json()
    assert body["reimbursed_paise"] == 300000
    assert body["reimbursement_balance_paise"] == 300000

    reimb2 = await client.post(f"/api/v1/billing/exam-fees/{exam['id']}/reimburse",
                               json={"amount_paise": 300000, "method": "cash",
                                     "date": "2026-11-25"},
                               headers=auth(w["admin"]))
    assert reimb2.status_code == 200
    assert reimb2.json()["status"] in ("reimbursed", "settled")

    # the reimbursement is a real payment with a receipt, allocated to the exam invoice
    async with TestSessionLocal() as db:
        pays = (await db.execute(select(Payment))).scalars().all()
        assert len(pays) == 2
        assert all(p.receipt_number for p in pays)
    stmt = (await client.get(f"/api/v1/billing/statement?student_id={w['a1_id']}",
                             headers=auth(w["admin"]))).json()
    assert stmt["students"][0]["exam_fees"][0]["reimbursed_paise"] == 600000


# ---------------------------------------------------------------------------
# 7-10. Online payments via webhook
# ---------------------------------------------------------------------------
async def _seed_order(invoice_id, order_id="order_fl_1", amount=450000):
    async with TestSessionLocal() as db:
        db.add(PaymentOrder(order_id=order_id, invoice_id=uuid.UUID(invoice_id),
                            amount_paise=amount, currency="INR", status="created"))
        await db.commit()


def _signed(body: dict, secret: str = WEBHOOK_SECRET):
    raw = json.dumps(body).encode()
    sig = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return raw, sig


@pytest.mark.asyncio
async def test_online_payment_confirmed_by_verified_webhook(client, world):
    """A valid captured event RECORDS the payment as pending — the fee is
    marked paid only after manual admin confirmation (manual fee policy)."""
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    await _seed_order(inv["id"])
    body = {"id": "evt_fl_1", "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_fl_1", "order_id": "order_fl_1",
                                               "amount": 450000, "currency": "INR",
                                               "method": "upi", "created": 1760000000}}}}
    raw, sig = _signed(body)
    r = await client.post("/api/v1/billing/webhooks/razorpay", content=raw,
                          headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending_verification"

    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert detail["status"] == "pending" and detail["amount_paid_paise"] == 0
    pays = (await client.get("/api/v1/billing/payments", headers=auth(w["admin"]))).json()
    assert pays[0]["source"] == "online"
    assert pays[0]["status"] == "pending_verification"

    conf = await client.post(f"/api/v1/billing/payments/{pays[0]['id']}/confirm", json={},
                             headers=auth(w["admin"]))
    assert conf.status_code == 200, conf.text
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert detail["status"] == "paid"
    assert conf.json()["receipt_number"]


@pytest.mark.asyncio
async def test_invalid_webhook_signature_rejected(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    await _seed_order(inv["id"], order_id="order_fl_2")
    body = {"id": "evt_fl_2", "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_fl_2", "order_id": "order_fl_2",
                                               "amount": 450000, "currency": "INR",
                                               "method": "card", "created": 1760000000}}}}
    raw = json.dumps(body).encode()
    bad = await client.post("/api/v1/billing/webhooks/razorpay", content=raw,
                            headers={"X-Razorpay-Signature": "bad", "Content-Type": "application/json"})
    assert bad.status_code == 400
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert detail["status"] == "pending"


@pytest.mark.asyncio
async def test_duplicate_webhook_no_duplicate_payment(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    await _seed_order(inv["id"], order_id="order_fl_3")
    body = {"id": "evt_fl_3", "event": "payment.captured",
            "payload": {"payment": {"entity": {"id": "pay_fl_3", "order_id": "order_fl_3",
                                               "amount": 450000, "currency": "INR",
                                               "method": "upi", "created": 1760000000}}}}
    raw, sig = _signed(body)
    headers = {"X-Razorpay-Signature": sig, "Content-Type": "application/json"}
    first = await client.post("/api/v1/billing/webhooks/razorpay", content=raw, headers=headers)
    assert first.status_code == 200
    second = await client.post("/api/v1/billing/webhooks/razorpay", content=raw, headers=headers)
    assert second.status_code == 200
    assert second.json()["status"] in ("duplicate_ignored", "already_recorded")

    async with TestSessionLocal() as db:
        assert len((await db.execute(select(Payment))).scalars().all()) == 1
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert detail["amount_paid_paise"] == 0       # no auto-paid state
    pays = (await client.get("/api/v1/billing/payments", headers=auth(w["admin"]))).json()
    conf = await client.post(f"/api/v1/billing/payments/{pays[0]['id']}/confirm", json={},
                             headers=auth(w["admin"]))
    assert conf.status_code == 200
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert detail["amount_paid_paise"] == 450000 and detail["status"] == "paid"


@pytest.mark.asyncio
async def test_failed_and_pending_events_do_not_mark_paid(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    await _seed_order(inv["id"], order_id="order_fl_4")

    # authorised (not captured) -> pending, charge untouched
    body_a = {"id": "evt_fl_4a", "event": "payment.authorized",
              "payload": {"payment": {"entity": {"id": "pay_fl_4a", "order_id": "order_fl_4",
                                                 "amount": 450000, "currency": "INR",
                                                 "method": "card", "created": 1760000000}}}}
    raw, sig = _signed(body_a)
    r = await client.post("/api/v1/billing/webhooks/razorpay", content=raw,
                          headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"})
    assert r.status_code == 200
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert detail["status"] == "pending"
    async with TestSessionLocal() as db:
        p = (await db.execute(select(Payment))).scalars().all()
        assert p[0].status == "pending_verification"

    # failed -> order failed, no payment
    body_f = {"id": "evt_fl_4b", "event": "payment.failed",
              "payload": {"payment": {"entity": {"id": "pay_fl_4b", "order_id": "order_fl_4",
                                                 "amount": 450000, "currency": "INR",
                                                 "method": "card", "created": 1760000000}}}}
    raw, sig = _signed(body_f)
    r2 = await client.post("/api/v1/billing/webhooks/razorpay", content=raw,
                           headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"})
    assert r2.status_code == 200
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert detail["status"] == "pending"
    assert detail["amount_paid_paise"] == 0


# ---------------------------------------------------------------------------
# 11. Family isolation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_family_ledger_isolation(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    await _manual_payment(client, w["admin"], 450000,
                          [{"invoice_id": inv["id"], "amount_paise": 450000}])

    # parent A sees family A statement only
    stmt_a = await client.get("/api/v1/billing/statement?family=1", headers=auth(w["pa"]))
    assert stmt_a.status_code == 200
    names = {s["student_name"] for s in stmt_a.json()["students"]}
    assert names == {"Al Pha"}

    # parent B sees nothing of family A
    stmt_b = await client.get("/api/v1/billing/statement?family=1", headers=auth(w["pb"]))
    assert stmt_b.json()["students"] == [] or "Al Pha" not in {
        s["student_name"] for s in stmt_b.json()["students"]}

    # student B cannot open family A's invoice or receipt
    inv_detail = await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["b1"]))
    assert inv_detail.status_code == 403
    pays = (await client.get("/api/v1/billing/payments", headers=auth(w["admin"]))).json()
    receipt = await client.get(f"/api/v1/billing/payments/{pays[0]['id']}/receipt", headers=auth(w["b1"]))
    assert receipt.status_code == 403

    # student A can see their own receipt
    ok = await client.get(f"/api/v1/billing/payments/{pays[0]['id']}/receipt", headers=auth(w["a1"]))
    assert ok.status_code == 200


# ---------------------------------------------------------------------------
# 12. Instructors blocked
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_instructors_blocked_from_financial_controls(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    for method, url, body in (
        ("post", "/api/v1/billing/payments/manual",
         {"amount_paise": 100, "method": "cash", "allocations": [{"invoice_id": inv["id"], "amount_paise": 100}]}),
        ("post", "/api/v1/billing/invoices",
         {"enrollment_id": str(w["e_a"]), "billing_month": "2027-02"}),
        ("post", "/api/v1/billing/generate-charges", {"billing_month": "2027-02"}),
        ("post", "/api/v1/billing/exam-fees", {"student_id": str(w["a1_id"]), "fee_charged_paise": 1}),
    ):
        r = await client.request(method, url, json=body, headers=auth(w["instructor"]))
        assert r.status_code == 403, url
    pays = await client.get("/api/v1/billing/payments", headers=auth(w["instructor"]))
    assert pays.status_code == 403
    stmt = await client.get("/api/v1/billing/statement?family=1", headers=auth(w["instructor"]))
    assert stmt.status_code == 403


# ---------------------------------------------------------------------------
# 13. Idempotent charge generation + per-class rule
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_generate_charges_idempotent_and_per_class_rule(client, world):
    w = world
    # per-class enrolment for student A (rate ₹1,200/class)
    async with TestSessionLocal() as db:
        e_pc = Enrollment(student_id=w["a1_id"], programme_id="ukulele", programme_name="Ukulele",
                          fee_plan="per_class", fee_amount=1200.0, status="active")
        db.add(e_pc)
        await db.commit()
        e_pc_id = e_pc.id

    # one completed class + one merely scheduled class in 2027-03
    from app.models.session import ClassSession
    async with TestSessionLocal() as db:
        for day, status in ((5, "completed"), (12, "scheduled")):
            db.add(ClassSession(enrollment_id=e_pc_id, student_id=w["a1_id"],
                                scheduled_date=date(2027, 3, day),
                                scheduled_start=time(17, 0), scheduled_end=time(18, 0),
                                timezone="Asia/Kolkata", status=status))
        await db.commit()

    run1 = await client.post("/api/v1/billing/generate-charges",
                             json={"billing_month": "2027-03", "due_day": 5},
                             headers=auth(w["admin"]))
    assert run1.status_code == 200, run1.text
    body = run1.json()
    amounts = {c["enrollment_id"]: c["amount_paise"] for c in body["created"]}
    # 4-class plan: 450000; 8-class plan: 800000; per-class: 1 COMPLETED class only
    assert amounts[str(w["e_a"])] == 450000
    assert amounts[str(w["e_b"])] == 800000
    assert amounts[str(e_pc_id)] == 120000   # never charges the scheduled class

    # repeat run creates nothing new
    run2 = await client.post("/api/v1/billing/generate-charges",
                             json={"billing_month": "2027-03"}, headers=auth(w["admin"]))
    assert run2.json()["created"] == []
    assert len(run2.json()["skipped"]) == 3

    async with TestSessionLocal() as db:
        invs = (await db.execute(select(Invoice).where(Invoice.billing_month == "2027-03"))).scalars().all()
        assert len(invs) == 3


# ---------------------------------------------------------------------------
# 14. Reversal with audit and correct balance
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_payment_reversal_audit_and_balance(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    pay = await _manual_payment(client, w["admin"], 450000,
                                [{"invoice_id": inv["id"], "amount_paise": 450000}])
    detail = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    allocation_id = detail["allocations"][0]["id"]

    rev = await client.post(f"/api/v1/billing/allocations/{allocation_id}/reverse",
                            json={"reason": "entry keyed against the wrong month"},
                            headers=auth(w["admin"]))
    assert rev.status_code == 200, rev.text

    after = (await client.get(f"/api/v1/billing/invoices/{inv['id']}", headers=auth(w["admin"]))).json()
    assert after["status"] == "pending"
    assert after["outstanding_paise"] == 450000

    audits = await db_audits("payment.allocation_reversed")
    assert audits and "wrong month" in (audits[0].summary or "")
    # original allocation is kept (negative reversal rows, nothing deleted)
    async with TestSessionLocal() as db:
        rows = (await db.execute(select(PaymentAllocation).where(
            PaymentAllocation.invoice_id == uuid.UUID(inv["id"])))).scalars().all()
        assert sum(r.amount_paise for r in rows) == 0
        assert any(r.amount_paise < 0 for r in rows)

    # double reversal refused
    again = await client.post(f"/api/v1/billing/allocations/{allocation_id}/reverse",
                              json={"reason": "again"}, headers=auth(w["admin"]))
    assert again.status_code in (400, 409)


# ---------------------------------------------------------------------------
# Extras: pending vs confirmed visible; void guard
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_void_refused_when_paid_and_stale_message_free(client, world):
    w = world
    inv = await _invoice(client, w["admin"], w["e_a"])
    await _manual_payment(client, w["admin"], 450000,
                          [{"invoice_id": inv["id"], "amount_paise": 450000}])
    void = await client.post(f"/api/v1/billing/invoices/{inv['id']}/void",
                             json={"reason": "testing"}, headers=auth(w["admin"]))
    assert void.status_code == 409

    inv2 = await _invoice(client, w["admin"], w["e_a"], month="2027-04")
    void2 = await client.post(f"/api/v1/billing/invoices/{inv2['id']}/void",
                              json={"reason": "duplicate charge for the same month"},
                              headers=auth(w["admin"]))
    assert void2.status_code == 200
    assert void2.json()["status"] == "void"
