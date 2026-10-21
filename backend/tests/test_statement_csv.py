"""
Student fee statement CSV: academy branding, plain-language headings,
paise→₹ conversion, meaningful credit-balance rows, no internal jargon,
and exports that never modify financial records.
"""
import csv
import io
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_statement_csv.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.admin import Admin
from app.models.student import Student
from app.models.enrollment import Enrollment
from app.models.billing import Invoice, Payment, PaymentAllocation
from app.models.finance import CreditLedgerEntry, ExamFee


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
        u = User(id=uuid.uuid4(), username="csvadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Csv", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _mk_student(username: str, name: str) -> tuple[uuid.UUID, uuid.UUID]:
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=username, hashed_password=get_password_hash("1234"),
                 role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        st = Student(id=uuid.uuid4(), user_id=u.id, cma_registration_id=f"CMA-2026-{username[:6]}",
                     portal_slug=username, first_name=name, last_name="T", status="active")
        s.add(st)
        await s.flush()
        e = Enrollment(id=uuid.uuid4(), student_id=st.id, programme_id="piano",
                       programme_name="Piano", fee_plan="4_classes", fee_amount=4500, status="active")
        s.add(e)
        await s.commit()
        return st.id, e.id


async def _export(client, admin, student_id) -> list[list[str]]:
    r = await client.get(f"/api/v1/billing/statement/export?student_id={student_id}",
                         headers=auth(admin))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


@pytest.mark.asyncio
async def test_statement_no_charges(client, admin_user):
    sid, _ = await _mk_student("nocharge", "NoCharge Kid")
    rows = await _export(client, admin_user, sid)
    flat = "\n".join(",".join(r) for r in rows)
    assert "CHANKARTS MUSIC ACADEMY" in flat
    assert "Student Fee Statement" in flat
    assert "NoCharge Kid" in flat
    assert "Currency" in flat and "INR (₹)" in flat
    assert "Generated" in flat
    # plain-language headings, no internal jargon anywhere
    header = next(r for r in rows if r and r[0] == "Student" and "Transaction Type" in r)
    assert "Amount Charged (₹)" in header and "Outstanding (₹)" in header
    assert "_paise" not in flat and "charged_paise" not in flat
    # zero credit stated correctly, blank cells for N/A
    credit_row = next(r for r in rows if len(r) > 1 and r[1] == "Available Credit Balance")
    assert "₹0.00" in credit_row


@pytest.mark.asyncio
async def test_statement_charge_and_payment(client, admin_user):
    sid, eid = await _mk_student("paidstu", "PaidStudent Kid")
    async with TestSessionLocal() as s:
        inv = Invoice(id=uuid.uuid4(), invoice_number="CSV/INV/0001", enrollment_id=eid, student_id=sid,
                      billing_month="2026-10", amount_paise=450000, amount_paid_paise=450000, status="paid")
        s.add(inv)
        await s.flush()
        p = Payment(id=uuid.uuid4(), invoice_id=inv.id, amount_paise=450000, currency="INR",
                    status="verified", method="upi", provider_payment_id="payCSV1",
                    paid_at=datetime(2026, 10, 5, 12, 0))
        s.add(p)
        await s.flush()
        s.add(PaymentAllocation(id=uuid.uuid4(), payment_id=p.id, invoice_id=inv.id,
                                enrollment_id=eid, student_id=sid, amount_paise=450000))
        await s.commit()
    rows = await _export(client, admin_user, sid)
    flat = "\n".join(",".join(r) for r in rows)
    charge = next(r for r in rows if len(r) > 5 and r[1] == "Fee Charge")
    assert charge[5] == "₹4,500.00"          # 450000 paise → ₹4,500.00
    assert charge[6] == "₹4,500.00" and charge[7] == "₹0.00"
    pay = next(r for r in rows if len(r) > 1 and r[1] == "Payment")
    assert pay[6] == "₹4,500.00"             # paid amount in Amount Paid column
    assert "credit_balance" not in flat


@pytest.mark.asyncio
async def test_statement_outstanding_balance(client, admin_user):
    sid, eid = await _mk_student("outst", "Outstanding Kid")
    async with TestSessionLocal() as s:
        inv = Invoice(id=uuid.uuid4(), invoice_number="CSV/INV/0002", enrollment_id=eid, student_id=sid,
                      billing_month="2026-10", amount_paise=450000, amount_paid_paise=200000,
                      status="partially_paid")
        s.add(inv)
        p = Payment(id=uuid.uuid4(), invoice_id=inv.id, amount_paise=200000, currency="INR",
                    status="verified", method="cash", paid_at=datetime(2026, 10, 6, 12, 0))
        s.add(p)
        await s.flush()
        s.add(PaymentAllocation(id=uuid.uuid4(), payment_id=p.id, invoice_id=inv.id,
                                enrollment_id=eid, student_id=sid, amount_paise=200000))
        await s.commit()
    rows = await _export(client, admin_user, sid)
    charge = next(r for r in rows if len(r) > 7 and r[1] == "Fee Charge")
    assert charge[6] == "₹2,000.00" and charge[7] == "₹2,500.00"


@pytest.mark.asyncio
async def test_statement_advance_credit_balance(client, admin_user):
    sid, _ = await _mk_student("creditst", "Credit Kid")
    async with TestSessionLocal() as s:
        s.add(CreditLedgerEntry(id=uuid.uuid4(), student_id=sid, kind="advance",
                                amount_paise=50000, note="Advance for November"))
        await s.commit()
    rows = await _export(client, admin_user, sid)
    credit_row = next(r for r in rows if len(r) > 1 and r[1] == "Available Credit Balance")
    assert "₹500.00" in credit_row
    assert "Credit available toward future charges" in credit_row
    # human label, not the technical field name
    assert not any("credit_balance" in ",".join(r) for r in rows)


@pytest.mark.asyncio
async def test_statement_multiple_transactions_and_exam_fee(client, admin_user):
    sid, eid = await _mk_student("multitx", "MultiTx Kid")
    async with TestSessionLocal() as s:
        inv1 = Invoice(id=uuid.uuid4(), invoice_number="CSV/INV/0003", enrollment_id=eid, student_id=sid,
                       billing_month="2026-10", amount_paise=450000, status="pending")
        inv2 = Invoice(id=uuid.uuid4(), invoice_number="CSV/INV/0004", enrollment_id=eid, student_id=sid,
                       billing_month="2026-09", amount_paise=450000, status="pending")
        s.add_all([inv1, inv2])
        s.add(ExamFee(id=uuid.uuid4(), student_id=sid, enrollment_id=eid, board="Trinity",
                      grade_level="Grade 1", fee_charged_paise=125050, academy_paid_paise=100000,
                      reimbursed_paise=0, status="charged"))
        await s.commit()
    rows = await _export(client, admin_user, sid)
    charges = [r for r in rows if len(r) > 7 and r[1] == "Fee Charge"]
    assert len(charges) == 2
    exam = next(r for r in rows if len(r) > 7 and r[1] == "Exam Fee")
    assert exam[5] == "₹1,250.50"           # rounding check: 125050 paise
    totals = next(r for r in rows if len(r) > 5 and r[1] == "TOTAL")
    assert totals[5] == "₹9,000.00"         # tuition charges only (exam fee is its own row)


@pytest.mark.asyncio
async def test_export_does_not_modify_financial_records(client, admin_user):
    sid, eid = await _mk_student("immutable", "Immutable Kid")
    async with TestSessionLocal() as s:
        inv = Invoice(id=uuid.uuid4(), invoice_number="CSV/INV/0005", enrollment_id=eid, student_id=sid,
                      billing_month="2026-10", amount_paise=450000, status="pending")
        s.add(inv)
        await s.commit()
    before = await _export(client, admin_user, sid)
    after = await _export(client, admin_user, sid)
    assert before == after
    async with TestSessionLocal() as s:
        inv = (await s.execute(select(Invoice).where(Invoice.invoice_number == "CSV/INV/0005"))).scalar_one()
        assert inv.amount_paise == 450000 and inv.status == "pending"
        count = (await s.execute(select(Invoice).where(Invoice.student_id == sid))).scalars().all()
        assert len(count) == 1
