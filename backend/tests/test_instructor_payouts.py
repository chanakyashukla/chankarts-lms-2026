"""
Employment categories, configurable rates (effective dates, precedence) and
the monthly completed-class payout calculation + payout lifecycle.
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_payouts.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.admin import Admin
from app.models.instructor import Instructor
from app.models.student import Student
from app.models.enrollment import Enrollment
from app.models.session import ClassSession
from app.models.billing import Invoice, Payment, PaymentAllocation
from app.models.instructor_payout import InstructorRateRule


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


async def _mk_instructor(username: str, employment=None) -> tuple[uuid.UUID, uuid.UUID]:
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=username, hashed_password=get_password_hash("1234"),
                 role=UserRole.INSTRUCTOR, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        i = Instructor(id=uuid.uuid4(), user_id=u.id, first_name=username.title(), last_name="Teach",
                       is_active=True, employment_type=employment)
        s.add(i)
        await s.commit()
        return i.id, u.id


async def _mk_pair(student_user: str, instructor_id, fee_plan="4_classes") -> tuple[uuid.UUID, uuid.UUID]:
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=student_user, hashed_password=get_password_hash("1234"),
                 role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        st = Student(id=uuid.uuid4(), user_id=u.id, cma_registration_id=f"CMA-2026-{uuid.uuid4().hex[:4].upper()}",
                     portal_slug=student_user, first_name=student_user.title(), last_name="S", status="active")
        s.add(st)
        await s.flush()
        e = Enrollment(id=uuid.uuid4(), student_id=st.id, programme_id="piano", programme_name="Piano",
                       instructor_id=instructor_id, fee_plan=fee_plan,
                       fee_amount=4500 if fee_plan == "4_classes" else 8000, status="active")
        s.add(e)
        await s.commit()
        return st.id, e.id


async def _mk_session(student_id, enrollment_id, instructor_id, d, st_, en_, status="scheduled") -> uuid.UUID:
    async with TestSessionLocal() as s:
        row = ClassSession(id=uuid.uuid4(), enrollment_id=enrollment_id, student_id=student_id,
                           instructor_id=instructor_id, scheduled_date=d, scheduled_start=st_,
                           scheduled_end=en_, status=status)
        s.add(row)
        await s.commit()
        return row.id


async def _complete(session_id, admin_tok, actual_date: str):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        return await c.post(f"/api/v1/sessions/{session_id}/complete",
                            json={"actual_date": actual_date}, headers=admin_tok)


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_category_defaults_are_separate_and_individual_overrides(client, admin_user):
    h = auth(admin_user)
    ins_id, _ = await _mk_instructor("catins", employment="intern")
    # intern default and regular default configured independently
    r = await client.put("/api/v1/admin/instructor-rates", json={
        "category": "intern", "per_class_rate_paise": 20000, "effective_from": "2026-01-01"}, headers=h)
    assert r.status_code == 200, r.text
    r = await client.put("/api/v1/admin/instructor-rates", json={
        "category": "regular", "per_class_rate_paise": 50000, "effective_from": "2026-01-01"}, headers=h)
    assert r.status_code == 200
    # intern does NOT inherit the regular rate
    r = await client.get(f"/api/v1/admin/instructors/{ins_id}/rate", headers=h)
    assert r.json()["current"]["rate_paise"] == 20000 and r.json()["current"]["source"] == "category"
    # individual agreement overrides from its effective date
    r = await client.post(f"/api/v1/admin/instructors/{ins_id}/rate", json={
        "per_class_rate_paise": 30000, "effective_from": "2026-06-01"}, headers=h)
    assert r.status_code == 200
    # before the individual effective date → category default still applies
    from app.models.instructor_payout import InstructorRateRule as _R  # noqa
    # (current uses today; build a fresh instructor with ONLY a future individual rule)
    ins2, _ = await _mk_instructor("futins", employment="regular")
    r = await client.post(f"/api/v1/admin/instructors/{ins2}/rate", json={
        "per_class_rate_paise": 99900, "effective_from": "2099-01-01"}, headers=h)
    assert r.status_code == 200
    r = await client.get(f"/api/v1/admin/instructors/{ins2}/rate", headers=h)
    cur = r.json()["current"]
    assert cur["rate_paise"] == 50000 and cur["source"] == "category", cur   # future rule not yet active
    hist = r.json()["individual_history"]
    assert hist[0]["per_class_rate_paise"] == 99900                          # history preserved
    # invalid inputs rejected
    r = await client.put("/api/v1/admin/instructor-rates", json={
        "category": "president", "per_class_rate_paise": 1, "effective_from": "2026-01-01"}, headers=h)
    assert r.status_code == 400
    r = await client.put("/api/v1/admin/instructor-rates", json={
        "category": "intern", "per_class_rate_paise": -5, "effective_from": "2026-01-01"}, headers=h)
    assert r.status_code == 400
    # changing a default appends (does not rewrite) history
    async with TestSessionLocal() as s:
        intern_rules = (await s.execute(select(_R).where(_R.category == "intern"))).scalars().all()
        assert len(intern_rules) == 1
    r = await client.put("/api/v1/admin/instructor-rates", json={
        "category": "intern", "per_class_rate_paise": 25000, "effective_from": "2026-09-01"}, headers=h)
    assert r.status_code == 200
    async with TestSessionLocal() as s:
        intern_rules = (await s.execute(select(_R).where(_R.category == "intern"))).scalars().all()
        assert len(intern_rules) == 2     # append-only; old rule intact


@pytest.mark.asyncio
async def test_payout_counts_only_completed_and_correct_month(client, admin_user):
    h = auth(admin_user)
    ins, _ = await _mk_instructor("p1", employment="regular")
    sid, eid = await _mk_pair("pstu1", ins, fee_plan="8_classes")
    await client.put("/api/v1/admin/instructor-rates", json={
        "category": "regular", "per_class_rate_paise": 50000, "effective_from": "2026-01-01"}, headers=h)

    sched = await _mk_session(sid, eid, ins, date(2026, 11, 3), time(10, 0), time(11, 0), status="scheduled")
    cancelled = await _mk_session(sid, eid, ins, date(2026, 11, 4), time(10, 0), time(11, 0), status="cancelled")
    done = await _mk_session(sid, eid, ins, date(2026, 11, 5), time(10, 0), time(11, 0))
    r = await _complete(str(done), h, "2026-11-05")
    assert r.status_code == 200, r.text
    # completed AGAIN — must not double-count
    await _complete(str(done), h, "2026-11-05")

    calc = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    assert calc["completed_count"] == 1                       # scheduled/cancelled never counted
    assert calc["payable_paise"] == 50000
    assert calc["outstanding_paise"] == 50000 and calc["paid_paise"] == 0
    assert calc["status"] == "calculated"
    # wrong month → nothing
    calc2 = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-12", headers=h)).json()
    assert calc2["completed_count"] == 0 and calc2["payable_paise"] == 0
    # completion in another month (actual_date drives attribution)
    done2 = await _mk_session(sid, eid, ins, date(2026, 11, 28), time(10, 0), time(11, 0))
    r = await _complete(str(done2), h, "2026-12-01")
    assert r.status_code == 200
    calc_dec = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-12", headers=h)).json()
    calc_nov = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    assert calc_dec["completed_count"] == 1 and calc_nov["completed_count"] == 1
    # student plan must not drive payout: complete a 3rd class regardless of4/8 plan
    done3 = await _mk_session(sid, eid, ins, date(2026, 11, 6), time(10, 0), time(11, 0))
    await _complete(str(done3), h, "2026-11-06")
    calc = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    assert calc["completed_count"] == 2 and calc["payable_paise"] == 100000


@pytest.mark.asyncio
async def test_rate_not_configured_blocks_review_and_payout(client, admin_user):
    h = auth(admin_user)
    ins, _ = await _mk_instructor("norrate", employment=None)   # no category, no individual rate
    sid, eid = await _mk_pair("pstu2", ins)
    done = await _mk_session(sid, eid, ins, date(2026, 11, 3), time(10, 0), time(11, 0))
    await _complete(str(done), h, "2026-11-05")
    calc = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    assert calc["status"] == "rate_not_configured"
    assert calc["payable_paise"] is None and calc["missing_rate_session_ids"]
    r = await client.post(f"/api/v1/admin/instructors/{ins}/payout-review",
                          json={"month": "2026-11"}, headers=h)
    assert r.status_code == 409
    r = await client.post(f"/api/v1/admin/instructors/{ins}/payouts",
                          json={"month": "2026-11", "amount_paise": 100, "method": "upi"}, headers=h)
    assert r.status_code == 409
    # configuring the rate unblocks everything
    r = await client.post(f"/api/v1/admin/instructors/{ins}/rate", json={
        "per_class_rate_paise": 40000, "effective_from": "2026-01-01"}, headers=h)
    assert r.status_code == 200
    calc = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    assert calc["payable_paise"] == 40000 and calc["status"] == "calculated"
    r = await client.post(f"/api/v1/admin/instructors/{ins}/payout-review",
                          json={"month": "2026-11"}, headers=h)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_mid_month_rate_change_per_session(client, admin_user):
    h = auth(admin_user)
    ins, _ = await _mk_instructor("midrate", employment="part_time")
    sid, eid = await _mk_pair("pstu3", ins)
    await client.post(f"/api/v1/admin/instructors/{ins}/rate", json={
        "per_class_rate_paise": 30000, "effective_from": "2026-11-01"}, headers=h)
    await client.post(f"/api/v1/admin/instructors/{ins}/rate", json={
        "per_class_rate_paise": 35000, "effective_from": "2026-11-15"}, headers=h)
    s1 = await _mk_session(sid, eid, ins, date(2026, 11, 5), time(10, 0), time(11, 0))
    s2 = await _mk_session(sid, eid, ins, date(2026, 11, 20), time(10, 0), time(11, 0))
    await _complete(str(s1), h, "2026-11-05")
    await _complete(str(s2), h, "2026-11-20")
    calc = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    rates = sorted(b["rate_paise"] for b in calc["rate_breakdown"])
    assert rates == [30000, 35000]
    assert calc["payable_paise"] == 65000                 # 1×300 + 1×350, NOT2×350


@pytest.mark.asyncio
async def test_different_instructors_different_rates(client, admin_user):
    h = auth(admin_user)
    a, _ = await _mk_instructor("rA", employment="regular")
    b, _ = await _mk_instructor("rB", employment="contract")
    await client.put("/api/v1/admin/instructor-rates", json={
        "category": "regular", "per_class_rate_paise": 50000, "effective_from": "2026-01-01"}, headers=h)
    await client.put("/api/v1/admin/instructor-rates", json={
        "category": "contract", "per_class_rate_paise": 70000, "effective_from": "2026-01-01"}, headers=h)
    sa_, ea = await _mk_pair("dupa", a)
    sb_, eb = await _mk_pair("dupb", b)
    for ins, sid, eid in ((a, sa_, ea), (b, sb_, eb)):
        sess = await _mk_session(sid, eid, ins, date(2026, 11, 3), time(10, 0), time(11, 0))
        await _complete(str(sess), h, "2026-11-05")
    ca = (await client.get(f"/api/v1/admin/instructors/{a}/payouts?month=2026-11", headers=h)).json()
    cb = (await client.get(f"/api/v1/admin/instructors/{b}/payouts?month=2026-11", headers=h)).json()
    assert ca["payable_paise"] == 50000 and cb["payable_paise"] == 70000
    # admin summary shows both rows
    summ = (await client.get("/api/v1/admin/payouts/summary?month=2026-11", headers=h)).json()
    by_name = {r["name"]: r for r in summ["rows"]}
    assert by_name["Ra Teach"]["payable_paise"] == 50000
    assert by_name["Rb Teach"]["payable_paise"] == 70000


@pytest.mark.asyncio
async def test_payout_lifecycle_partial_review_duplicate_reverse(client, admin_user):
    h = auth(admin_user)
    ins, ins_user = await _mk_instructor("life", employment="regular")
    sid, eid = await _mk_pair("plife", ins)
    await client.put("/api/v1/admin/instructor-rates", json={
        "category": "regular", "per_class_rate_paise": 50000, "effective_from": "2026-01-01"}, headers=h)
    for d in ("2026-11-03", "2026-11-10", "2026-11-17"):
        sess = await _mk_session(sid, eid, ins, date.fromisoformat(d), time(10, 0), time(11, 0))
        await _complete(str(sess), h, d)
    calc = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    assert calc["payable_paise"] == 150000

    # partial payout
    r = await client.post(f"/api/v1/admin/instructors/{ins}/payouts", json={
        "month": "2026-11", "amount_paise": 60000, "method": "upi",
        "paid_at": "2026-11-30", "reference": "TX-1"}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "partially_paid" and r.json()["outstanding_paise"] == 90000
    # duplicate identical payout refused
    r = await client.post(f"/api/v1/admin/instructors/{ins}/payouts", json={
        "month": "2026-11", "amount_paise": 60000, "method": "upi",
        "paid_at": "2026-11-30", "reference": "TX-1"}, headers=h)
    assert r.status_code == 409
    # overpay blocked
    r = await client.post(f"/api/v1/admin/instructors/{ins}/payouts", json={
        "month": "2026-11", "amount_paise": 999999, "method": "upi", "paid_at": "2026-11-30"}, headers=h)
    assert r.status_code == 400
    # second payout completes the month
    r = await client.post(f"/api/v1/admin/instructors/{ins}/payouts", json={
        "month": "2026-11", "amount_paise": 90000, "method": "bank_transfer",
        "paid_at": "2026-12-02", "reference": "TX-2"}, headers=h)
    assert r.status_code == 201 and r.json()["status"] == "paid"
    # review works while paid
    r = await client.post(f"/api/v1/admin/instructors/{ins}/payout-review",
                          json={"month": "2026-11"}, headers=h)
    assert r.status_code == 200
    calc = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    assert calc["reviewed"]["payable_at_review"] == 150000

    # reverse one payout → adjustment recorded, math stays consistent
    pid = calc["payouts"][0]["id"]
    r = await client.post(f"/api/v1/admin/payouts/{pid}/reverse", json={"reason": "wrong transfer"}, headers=h)
    assert r.status_code == 200
    calc = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    assert calc["paid_paise"] == 90000
    assert any(p["kind"] == "adjustment" and p["amount_paise"] == -60000 for p in calc["payouts"])
    # reversing twice refused
    r = await client.post(f"/api/v1/admin/payouts/{pid}/reverse", json={"reason": "x"}, headers=h)
    assert r.status_code == 409
    # review flagged changed_since_review after reversal altered paid? payable unchanged:
    calc = (await client.get(f"/api/v1/admin/instructors/{ins}/payouts?month=2026-11", headers=h)).json()
    assert calc["payable_paise"] == 150000 and calc["paid_paise"] == 90000
    assert calc["outstanding_paise"] == 60000


@pytest.mark.asyncio
async def test_reassignment_uses_session_instructor_and_preserves_student_finance(client, admin_user):
    h = auth(admin_user)
    a, _ = await _mk_instructor("origA", employment="regular")
    b, _ = await _mk_instructor("movedB", employment="regular")
    await client.put("/api/v1/admin/instructor-rates", json={
        "category": "regular", "per_class_rate_paise": 50000, "effective_from": "2026-01-01"}, headers=h)
    sid, eid = await _mk_pair("reass", a)
    # student financial record that must never be touched by payout logic
    async with TestSessionLocal() as s:
        inv = Invoice(id=uuid.uuid4(), invoice_number="PAY-PRES/0001", enrollment_id=eid, student_id=sid,
                      billing_month="2026-11", amount_paise=450000, status="pending")
        s.add(inv)
        await s.commit()
        inv_id = inv.id
    sess = await _mk_session(sid, eid, a, date(2026, 11, 4), time(10, 0), time(11, 0))
    await _complete(str(sess), h, "2026-11-05")
    ca = (await client.get(f"/api/v1/admin/instructors/{a}/payouts?month=2026-11", headers=h)).json()
    assert ca["payable_paise"] == 50000
    # authorised reassignment of the completed session's attribution
    async with TestSessionLocal() as s:
        row = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(str(sess))))).scalar_one()
        row.instructor_id = b
        s.add(row)
        await s.commit()
    ca = (await client.get(f"/api/v1/admin/instructors/{a}/payouts?month=2026-11", headers=h)).json()
    cb = (await client.get(f"/api/v1/admin/instructors/{b}/payouts?month=2026-11", headers=h)).json()
    assert ca["payable_paise"] == 0 and cb["payable_paise"] == 50000   # follows the session's instructor
    # student invoice untouched
    async with TestSessionLocal() as s:
        inv = (await s.execute(select(Invoice).where(Invoice.id == uuid.UUID(str(inv_id))))).scalar_one()
        assert inv.amount_paise == 450000 and inv.status == "pending" and inv.student_id == sid


@pytest.mark.asyncio
async def test_access_control_payouts(client, admin_user):
    h = auth(admin_user)
    ins_a, user_a = await _mk_instructor("secA", employment="regular")
    ins_b, user_b = await _mk_instructor("secB", employment="regular")
    await client.put("/api/v1/admin/instructor-rates", json={
        "category": "regular", "per_class_rate_paise": 50000, "effective_from": "2026-01-01"}, headers=h)
    sid, eid = await _mk_pair("secstu", ins_a)
    sess = await _mk_session(sid, eid, ins_a, date(2026, 11, 4), time(10, 0), time(11, 0))
    await _complete(str(sess), h, "2026-11-05")
    tok_a = {"Authorization": f"Bearer {create_access_token(data={'sub': str(user_a), 'role': 'instructor'}, expires_delta=timedelta(minutes=30))}"}
    # instructor sees OWN payout only
    r = await client.get("/api/v1/admin/payouts/self?month=2026-11", headers=tok_a)
    assert r.status_code == 200 and r.json()["instructor"]["id"] == str(ins_a)
    assert r.json()["payable_paise"] == 50000
    # instructors cannot use admin payout endpoints
    r = await client.get(f"/api/v1/admin/instructors/{ins_b}/payouts?month=2026-11", headers=tok_a)
    assert r.status_code == 403
    r = await client.get("/api/v1/admin/payouts/summary?month=2026-11", headers=tok_a)
    assert r.status_code == 403
    r = await client.post(f"/api/v1/admin/instructors/{ins_a}/payouts",
                          json={"month": "2026-11", "amount_paise": 100, "method": "upi"}, headers=tok_a)
    assert r.status_code == 403
    r = await client.put(f"/api/v1/admin/instructor-rates", json={
        "category": "intern", "per_class_rate_paise": 1, "effective_from": "2026-01-01"}, headers=tok_a)
    assert r.status_code == 403
    # students cannot either (reuse the student user created above)
    async with TestSessionLocal() as s:
        su_id = (await s.execute(select(User.id).where(User.username == "secstu"))).scalar_one()
    tok_s = {"Authorization": f"Bearer {create_access_token(data={'sub': str(su_id), 'role': 'student'}, expires_delta=timedelta(minutes=30))}"}
    r = await client.get("/api/v1/admin/payouts/summary?month=2026-11", headers=tok_s)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_payout_csv_export_branded(client, admin_user):
    h = auth(admin_user)
    ins, _ = await _mk_instructor("csvins", employment="regular")
    sid, eid = await _mk_pair("csvstu", ins)
    await client.put("/api/v1/admin/instructor-rates", json={
        "category": "regular", "per_class_rate_paise": 50000, "effective_from": "2026-01-01"}, headers=h)
    sess = await _mk_session(sid, eid, ins, date(2026, 11, 4), time(10, 0), time(11, 0))
    await _complete(str(sess), h, "2026-11-05")
    r = await client.get(f"/api/v1/admin/instructors/{ins}/payouts/export?month=2026-11", headers=h)
    assert r.status_code == 200
    txt = r.content.decode("utf-8-sig")
    assert "CHANKARTS MUSIC ACADEMY" in txt and "Instructor Monthly Teaching & Payout Statement" in txt
    assert "500.00" in txt and "2026-11" in txt
