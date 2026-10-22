"""
Payment-claim workflow: enriched pending list, rejection with reason/message/
attachment (support-system integration + portal visibility), clarification
without status change, manual/partial verification semantics, idempotency and
the guarantee that rejections never touch invoices, allocations or totals.
"""
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_payment_claims.db"
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
from app.models.billing import Invoice, Payment, PaymentAllocation
from app.models.support import SupportRequest, SupportReply, SupportAttachment
from app.models.finance import Receipt
from app.models.audit import AuditEvent


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
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    app.dependency_overrides.pop(get_db, None)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def admin_user():
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username="payadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Pay", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _mk_claim(username="claimkid", amount=450000, paid=0) -> dict:
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=username, hashed_password=get_password_hash("1234"),
                 role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        st = Student(id=uuid.uuid4(), user_id=u.id, cma_registration_id=f"CMA-2026-{username[:5].upper()}",
                     portal_slug=username, first_name="Claim", last_name="Kid", status="active")
        s.add(st)
        await s.flush()
        e = Enrollment(id=uuid.uuid4(), student_id=st.id, programme_id="piano",
                       programme_name="Piano", fee_plan="4_classes", fee_amount=4500,
                       status="active")
        s.add(e)
        await s.flush()
        inv = Invoice(id=uuid.uuid4(), invoice_number=f"CLM/INV/{username[:6]}", enrollment_id=e.id,
                      student_id=st.id, billing_month="2026-10", amount_paise=amount,
                      amount_paid_paise=paid, status="paid" if paid >= amount else
                      ("partially_paid" if paid else "pending"))
        s.add(inv)
        await s.flush()
        pay = Payment(id=uuid.uuid4(), invoice_id=inv.id, payer_user_id=u.id,
                      amount_paise=amount, currency="INR", method="upi",
                      provider_payment_id=f"REF-{username[:8].upper()}",
                      status="pending_verification", paid_at=datetime(2026, 10, 21, 12, 0),
                      source="reported")
        s.add(pay)
        await s.commit()
        return {"user": u.id, "student": st.id, "enrollment": e.id,
                "invoice": inv.id, "payment": pay.id}


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pending_list_is_enriched(client, admin_user):
    h = auth(admin_user)
    claim = await _mk_claim("enrich")
    # an unresolvable claim (no invoice, no payer) must be flagged, not guessed
    async with TestSessionLocal() as s:
        s.add(Payment(id=uuid.uuid4(), amount_paise=10000, currency="INR", method="cash",
                      status="pending_verification", source="reported",
                      provider_payment_id="ORPHAN-1"))
        await s.commit()
    r = await client.get("/api/v1/billing/payments?status=pending_verification", headers=h)
    assert r.status_code == 200
    rows = {p["id"]: p for p in r.json()}
    linked = rows[str(claim["payment"])]
    assert linked["student_name"] == "Claim Kid"
    assert linked["expected_paise"] == 450000
    assert linked["invoice_number"] and linked["fee_label"]
    assert linked["claim_unlinked"] is False
    orphan = next(p for p in rows.values() if p["provider_payment_id"] == "ORPHAN-1")
    assert orphan["claim_unlinked"] is True and orphan["student_name"] is None


@pytest.mark.asyncio
async def test_reject_claim_with_reason_message_and_attachment(client, admin_user):
    h = auth(admin_user)
    claim = await _mk_claim("rejectme")
    async with TestSessionLocal() as s:
        receipts_before = (await s.execute(select(func.count(Receipt.id)))).scalar()
        alloc_before = (await s.execute(select(func.count(PaymentAllocation.id)))).scalar()

    r = await client.post(f"/api/v1/billing/payments/{claim['payment']}/reject",
        data={"reason": "Amount is below the required amount",
              "message": "The amount reported is lower than the selected package fee."},
        files={"file": ("proof.png", PNG, "image/png")}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rejected"] is True and body["claim_unlinked"] is False
    thread_id = body["support_request_id"]
    assert thread_id

    async with TestSessionLocal() as s:
        pay = (await s.execute(select(Payment).where(Payment.id == uuid.UUID(str(claim["payment"]))))).scalar_one()
        assert pay.status == "rejected"
        assert "Rejected [Amount is below the required amount]" in pay.notes
        inv = (await s.execute(select(Invoice).where(Invoice.id == uuid.UUID(str(claim["invoice"]))))).scalar_one()
        # invoice untouched — a rejected claim never marks anything paid
        assert inv.amount_paid_paise == 0 and inv.status == "pending"
        assert (await s.execute(select(func.count(PaymentAllocation.id)))).scalar() == alloc_before
        assert (await s.execute(select(func.count(Receipt.id)))).scalar() == receipts_before
        # support thread linked to the right student + attachment validated+stored
        thread = (await s.execute(select(SupportRequest).where(
            SupportRequest.id == uuid.UUID(thread_id)))).scalar_one()
        assert thread.related_student_id == uuid.UUID(str(claim["student"]))
        assert thread.sender_role == "admin"
        atts = (await s.execute(select(SupportAttachment).where(
            SupportAttachment.request_id == thread.id))).scalars().all()
        assert len(atts) == 1 and atts[0].content_type == "image/png"
        # audit trail records who rejected it
        ev = (await s.execute(select(AuditEvent).where(
            AuditEvent.action == "payment.claim_rejected"))).scalars().all()
        assert ev and str(claim["payment"]) in (ev[-1].entity_id or "")

    # idempotent: rejecting twice is refused
    r2 = await client.post(f"/api/v1/billing/payments/{claim['payment']}/reject",
                           data={"reason": "Duplicate payment submission"}, headers=h)
    assert r2.status_code == 409 and "already been rejected" in r2.json()["detail"]

    # student portal sees the response + can reply + fetch the attachment
    stu_tok = create_access_token(data={"sub": str(claim["user"]), "role": "student"},
                                  expires_delta=timedelta(minutes=30))
    sh = {"Authorization": f"Bearer {stu_tok}"}
    lst = await client.get("/api/v1/portal/support", headers=sh)
    assert lst.status_code == 200
    assert any(t["id"] == thread_id for t in lst.json())
    det = await client.get(f"/api/v1/portal/support/{thread_id}", headers=sh)
    assert det.status_code == 200
    assert "below the required amount" in det.json()["message"] or det.json()["attachments"]
    rep = await client.post(f"/api/v1/portal/support/{thread_id}/reply",
                            json={"body": "I will re-check the amount with the bank."}, headers=sh)
    assert rep.status_code == 201
    # attachment served to the participant, not anonymously
    stored = det.json()["attachments"][0]["stored_name"]
    anon = await client.get(f"/api/v1/portal/support/files/{stored}")
    assert anon.status_code in (401, 403, 404)
    authed = await client.get(f"/api/v1/portal/support/files/{stored}", headers=sh)
    assert authed.status_code == 200 and authed.content[:4] == b"\x89PNG"


@pytest.mark.asyncio
async def test_reject_server_side_file_validation(client, admin_user):
    h = auth(admin_user)
    claim = await _mk_claim("badfiles")
    r = await client.post(f"/api/v1/billing/payments/{claim['payment']}/reject",
        data={"reason": "Invalid or missing proof"},
        files={"file": ("evil.txt", b"plain text not an image", "text/plain")}, headers=h)
    assert r.status_code == 400 and "Unsupported file type" in r.json()["detail"]
    # oversized payload rejected by size limit (magic bytes valid)
    big = PNG + b"0" * ((get_settings().MAX_UPLOAD_MB * 1024 * 1024) + 16)
    r = await client.post(f"/api/v1/billing/payments/{claim['payment']}/reject",
        data={"reason": "Invalid or missing proof"},
        files={"file": ("big.png", big, "image/png")}, headers=h)
    assert r.status_code == 400 and "MB limit" in r.json()["detail"]
    # claim untouched by failed uploads
    async with TestSessionLocal() as s:
        pay = (await s.execute(select(Payment).where(Payment.id == uuid.UUID(str(claim["payment"]))))).scalar_one()
        assert pay.status == "pending_verification"


@pytest.mark.asyncio
async def test_clarify_keeps_claim_pending(client, admin_user):
    h = auth(admin_user)
    claim = await _mk_claim("clarifyme")
    r = await client.post(f"/api/v1/billing/payments/{claim['payment']}/clarify",
                          data={"message": "Please share the UPI reference screenshot."}, headers=h)
    assert r.status_code == 200, r.text
    async with TestSessionLocal() as s:
        pay = (await s.execute(select(Payment).where(Payment.id == uuid.UUID(str(claim["payment"]))))).scalar_one()
        assert pay.status == "pending_verification"     # unchanged
        assert "Clarification requested" in pay.notes
        thread = (await s.execute(select(SupportRequest))).scalars().all()
        assert any(t.related_student_id == uuid.UUID(str(claim["student"])) for t in thread)


@pytest.mark.asyncio
async def test_confirm_partial_payment_and_double_confirm(client, admin_user):
    h = auth(admin_user)
    claim = await _mk_claim("partial", amount=450000)
    # shrink the reported payment to a genuine partial amount (underpayment case)
    async with TestSessionLocal() as s:
        pay = (await s.execute(select(Payment).where(Payment.id == uuid.UUID(str(claim["payment"]))))).scalar_one()
        pay.amount_paise = 100000
        s.add(pay)
        await s.commit()

    r = await client.post(f"/api/v1/billing/payments/{claim['payment']}/confirm",
                          json={"note": "matched UPI statement"}, headers=h)
    assert r.status_code == 200, r.text
    async with TestSessionLocal() as s:
        inv = (await s.execute(select(Invoice).where(Invoice.id == uuid.UUID(str(claim["invoice"]))))).scalar_one()
        assert inv.amount_paid_paise == 100000
        assert inv.status == "partially_paid"
        assert inv.amount_paise - inv.amount_paid_paise == 350000   # outstanding stays accurate
        alloc = (await s.execute(select(PaymentAllocation).where(
            PaymentAllocation.payment_id == uuid.UUID(str(claim["payment"]))))).scalars().all()
        assert len(alloc) == 1 and alloc[0].amount_paise == 100000
    # idempotency: double confirmation refused
    r2 = await client.post(f"/api/v1/billing/payments/{claim['payment']}/confirm", json={}, headers=h)
    assert r2.status_code == 409
    # rejecting a VERIFIED payment must be refused (keeps financial integrity)
    r3 = await client.post(f"/api/v1/billing/payments/{claim['payment']}/reject",
                           data={"reason": "No payment received"}, headers=h)
    assert r3.status_code == 409 and "already verified" in r3.json()["detail"]


@pytest.mark.asyncio
async def test_rejection_never_changes_collected_totals(client, admin_user):
    h = auth(admin_user)
    claim = await _mk_claim("totals")
    st_res = await client.get("/api/v1/billing/reports/collections?billing_month=2026-10", headers=h)
    before = st_res.json()["totals"]
    await client.post(f"/api/v1/billing/payments/{claim['payment']}/reject",
                      data={"reason": "No payment received", "message": "Not received."}, headers=h)
    st2 = await client.get("/api/v1/billing/reports/collections?billing_month=2026-10", headers=h)
    after = st2.json()["totals"]
    assert after["collected_paise"] == before["collected_paise"]
    assert after["outstanding_paise"] == before["outstanding_paise"]
