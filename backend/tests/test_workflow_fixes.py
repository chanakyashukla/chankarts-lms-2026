"""
Workflow-fix tests: PIN recovery, role boundaries, reschedule lifecycle,
instructor assignment, account management, explicit provisioning.
"""
import re
import uuid
from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_workflow.db"
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
from app.models.class_schedule import ClassSchedule
from app.models.session import ClassSession
from app.models.pin_reset import PinResetRequest


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


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {_make_token(user)}"}


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


async def _mk_user(db, username, password, role, must_change=False):
    u = User(email=f"{username}@t.local" if "@" not in username else username,
             username=username, hashed_password=get_password_hash(password),
             role=role, is_active=True, must_change_pin=must_change)
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def admin_user():
    async with TestSessionLocal() as db:
        u = await _mk_user(db, "wfadmin", "AdminPass@123", UserRole.ADMIN)
        db.add(Admin(user_id=u.id, first_name="WF", last_name="Admin", admin_level="super_admin", is_active=True))
        await db.commit()
        return u


@pytest_asyncio.fixture
async def instructor_user():
    async with TestSessionLocal() as db:
        u = await _mk_user(db, "wfinst", "InstPass@123", UserRole.INSTRUCTOR)
        db.add(Instructor(user_id=u.id, first_name="WF", last_name="Faculty",
                          specializations="Piano", is_active=True))
        await db.commit()
        return u


async def _mk_student(db, suffix, enrolled_to=None):
    # must_change=False: these tests use direct tokens; the pin-reset test
    # sets the flag itself when the admin issues a temporary PIN
    u = await _mk_user(db, f"CMA-9{suffix:03d}", f"{1000 + suffix:04d}", UserRole.STUDENT, must_change=False)
    s = Student(user_id=u.id, cma_registration_id=f"CMA-2026-9{suffix:03d}",
                portal_slug=f"wfs{suffix}", first_name=f"Wf{suffix}", last_name="Student",
                status="active", profile_complete=False)
    db.add(s)
    await db.flush()
    e = Enrollment(student_id=s.id, programme_id="piano", programme_name="Piano",
                   instructor_id=enrolled_to, status="active")
    db.add(e)
    await db.flush()
    return u, s, e


@pytest_asyncio.fixture
async def student_a():
    async with TestSessionLocal() as db:
        out = await _mk_student(db, 1)
        await db.commit()
        return out


@pytest_asyncio.fixture
async def student_b():
    async with TestSessionLocal() as db:
        out = await _mk_student(db, 2)
        await db.commit()
        return out


# ---------------------------------------------------------------------------
# 1. Forgot PIN — generic response, no enumeration, admin issues temp PIN
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pin_reset_request_generic_and_no_enumeration(client, student_a, admin_user, instructor_user):
    # Unknown account → same generic response
    r1 = await client.post("/api/v1/auth/pin-reset-request",
                           json={"username": "CMA-4040", "contact": "9999900000"})
    assert r1.status_code == 201
    # Known account → identical generic response
    r2 = await client.post("/api/v1/auth/pin-reset-request",
                           json={"username": "CMA-9001", "contact": "9999900001", "details": "Forgot PIN"})
    assert r2.status_code == 201
    assert r1.json() == r2.json()
    assert "contact you using your registered contact details" in r2.json()["message"]

    # Only the real account produced a queue row
    async with TestSessionLocal() as db:
        rows = (await db.execute(select(PinResetRequest))).scalars().all()
        assert len(rows) == 1
        assert rows[0].username_submitted == "CMA-9001"

    # Instructor cannot see or approve the queue
    async with TestSessionLocal() as db:
        inst = (await db.execute(select(User).where(User.username == "wfinst"))).scalar_one()
    denied = await client.get("/api/v1/admin/pin-reset-requests", headers=auth(inst))
    assert denied.status_code == 403

    # Admin sees it
    queue = await client.get("/api/v1/admin/pin-reset-requests", headers=auth(admin_user))
    assert queue.status_code == 200
    item = queue.json()[0]
    assert item["account_login_id"] == "CMA-9001"

    # Admin issues a temporary PIN (once) + forced change
    res = await client.post(f"/api/v1/admin/pin-reset-requests/{item['id']}/approve", headers=auth(admin_user))
    assert res.status_code == 200
    pin = res.json()["new_pin"]
    assert re.fullmatch(r"\d{4}", pin) and res.json()["must_change_pin"] is True

    # Old PIN dead, new PIN logs in, portal blocked until change
    async with TestSessionLocal() as db:
        user = (await db.execute(select(User).where(User.username == "CMA-9001"))).scalar_one()
        assert user.must_change_pin is True
        assert user.hashed_password != pin
    login_old = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": "1001"})
    assert login_old.status_code == 401
    login_new = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": pin})
    assert login_new.status_code == 200
    token = login_new.json()["access_token"]
    blocked = await client.get("/api/v1/portal/me", headers={"Authorization": f"Bearer {token}"})
    assert blocked.status_code == 403 and blocked.json()["detail"] == "PIN_CHANGE_REQUIRED"
    ok = await client.post("/api/v1/auth/change-pin",
                           json={"current_pin": pin, "new_pin": "2468"},
                           headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    login_final = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": "2468"})
    assert login_final.status_code == 200 and login_final.json()["must_change_pin"] is False


# ---------------------------------------------------------------------------
# 2. Instructor cannot touch admin-only operations
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_instructor_cannot_touch_admin_apis(client, instructor_user, student_a):
    u, s, e = student_a
    async with TestSessionLocal() as db:
        inst = (await db.execute(select(Instructor).where(Instructor.user_id == instructor_user.id))).scalar_one()
        inst_id = inst.id
    h = auth(instructor_user)
    # accounts & credentials
    assert (await client.post("/api/v1/admin/students", json={"username": "x1234", "first_name": "X"}, headers=h)).status_code == 403
    assert (await client.post(f"/api/v1/admin/students/{s.id}/reset-pin", headers=h)).status_code == 403
    assert (await client.post("/api/v1/admin/instructors", json={"username": "x9876", "first_name": "Y"}, headers=h)).status_code == 403
    # fees
    assert (await client.post("/api/v1/billing/payments/manual", json={"amount_paise": 100, "method": "upi"}, headers=h)).status_code == 403
    assert (await client.post("/api/v1/billing/packages", json={"code": "p1", "name": "P", "sessions_included": 4, "fee_paise": 1}, headers=h)).status_code == 403
    # reschedule execution & queue
    assert (await client.get("/api/v1/sessions/reschedule-requests", headers=h)).status_code == 403
    # instructor assignment + pin queue + schedules
    assert (await client.post(f"/api/v1/admin/enrollments/{e.id}/instructor", json={"instructor_id": str(inst_id)}, headers=h)).status_code == 403
    assert (await client.get("/api/v1/admin/pin-reset-requests", headers=h)).status_code == 403
    assert (await client.get("/api/v1/admin/schedules", headers=h)).status_code == 403
    assert (await client.get("/api/v1/admin/students", headers=h)).status_code == 403


# ---------------------------------------------------------------------------
# 3. Student isolation + assignment scoping
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_student_isolation_and_assignment_scoping(client, student_a, student_b, admin_user):
    ua, sa, ea = student_a
    ub, sb, eb = student_b
    async with TestSessionLocal() as db:
        inst_user = await _mk_user(db, "wfinst2", "InstPass@123", UserRole.INSTRUCTOR)
        inst = Instructor(user_id=inst_user.id, first_name="WF2", last_name="Faculty", is_active=True)
        db.add(inst)
        await db.flush()
        ea.instructor_id = inst.id
        db.add(ea)
        await db.commit()
        inst_id = inst.id

    # instructor creates assignment only for assigned enrollment (ea ok, eb denied)
    h = auth((await _mk_user_lookup(inst_user.username)))
    ok = await client.post("/api/v1/learning/assignments", json={
        "enrollment_id": str(ea.id), "title": "Scales", "assigned_date": date.today().isoformat()}, headers=h)
    assert ok.status_code == 201
    assert ok.json()["created_by"]
    dup = await client.post("/api/v1/learning/assignments", json={
        "enrollment_id": str(ea.id), "title": "Scales", "assigned_date": date.today().isoformat()}, headers=h)
    assert dup.status_code == 409
    cross = await client.post("/api/v1/learning/assignments", json={
        "enrollment_id": str(eb.id), "title": "Other", "assigned_date": date.today().isoformat()}, headers=h)
    assert cross.status_code == 403

    # student A sees only own assignment
    ta = _tok(ua)
    tb = _tok(ub)
    a_list = await client.get("/api/v1/learning/assignments", headers={"Authorization": f"Bearer {ta}"})
    assert a_list.status_code == 200 and len(a_list.json()) == 1
    b_list = await client.get("/api/v1/learning/assignments", headers={"Authorization": f"Bearer {tb}"})
    assert b_list.status_code == 200 and len(b_list.json()) == 0
    # student cannot create assignments
    assert (await client.post("/api/v1/learning/assignments", json={
        "enrollment_id": str(ea.id), "title": "Hax"}, headers={"Authorization": f"Bearer {ta}"})).status_code == 403


def _tok(user: User) -> str:
    return _make_token(user)


async def _mk_user_lookup(username: str) -> User:
    async with TestSessionLocal() as db:
        return (await db.execute(select(User).where(User.username == username))).scalar_one()


# ---------------------------------------------------------------------------
# 4. Instructor assignment: conflicts, confirmation, visibility
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assign_instructor_conflicts_and_visibility(client, admin_user, student_a, student_b):
    ua, sa, ea = student_a
    ub, sb, eb = student_b
    async with TestSessionLocal() as db:
        inst_user = await _mk_user(db, "wfassign", "InstPass@123", UserRole.INSTRUCTOR)
        inst = Instructor(user_id=inst_user.id, first_name="WFA", last_name="Faculty",
                          specializations="Piano", is_active=True)
        db.add(inst)
        await db.flush()
        # two weekly rows that collide on Friday 18:00-19:00
        db.add(ClassSchedule(enrollment_id=ea.id, instructor_id=None, day_of_week="friday",
                             start_time=time(18, 0), end_time=time(19, 0), is_active=True))
        db.add(ClassSchedule(enrollment_id=eb.id, instructor_id=None, day_of_week="friday",
                             start_time=time(18, 30), end_time=time(19, 30), is_active=True))
        await db.commit()
        inst_id = inst.id

    h = auth(admin_user)

    # availability of instructor for A's slot
    av = await client.get(
        f"/api/v1/admin/instructors/{inst_id}/availability?day=friday&start=18:00&end=19:00&exclude_enrollment_id={ea.id}",
        headers=h)
    assert av.status_code == 200 and av.json()["available"] is True

    # assign A to instructor (no conflicts)
    r1 = await client.post(f"/api/v1/admin/enrollments/{ea.id}/instructor",
                           json={"instructor_id": str(inst_id)}, headers=h)
    assert r1.status_code == 200
    assert r1.json()["schedule_rows_updated"] == 1

    # assign B: conflicts with A's assigned slot → 409 without confirmation
    r2 = await client.post(f"/api/v1/admin/enrollments/{eb.id}/instructor",
                           json={"instructor_id": str(inst_id)}, headers=h)
    assert r2.status_code == 409
    assert "conflicts" in r2.json()["detail"]

    # confirmation allowed — nothing is silently moved or deleted
    async with TestSessionLocal() as db:
        rows_before = (await db.execute(select(ClassSchedule))).scalars().all()
    r3 = await client.post(f"/api/v1/admin/enrollments/{eb.id}/instructor",
                           json={"instructor_id": str(inst_id), "confirm_conflicts": True}, headers=h)
    assert r3.status_code == 200
    async with TestSessionLocal() as db:
        rows_after = (await db.execute(select(ClassSchedule))).scalars().all()
        assert len(rows_after) == len(rows_before) == 2
        # A's row still at its original time
        assert any(r.day_of_week == "friday" and r.start_time == time(18, 0) for r in rows_after)

    # instructor now sees BOTH assigned students only
    async with TestSessionLocal() as db:
        iu = (await db.execute(select(User).where(User.username == "wfassign"))).scalar_one()
    enrs = await client.get("/api/v1/portal/enrollments", headers=auth(iu))
    assert enrs.status_code == 200
    names = {e["student_name"] for e in enrs.json()}
    assert names == {"Wf1 Student", "Wf2 Student"}

    # unassign works and is audited
    r4 = await client.post(f"/api/v1/admin/enrollments/{ea.id}/instructor",
                           json={"instructor_id": None}, headers=h)
    assert r4.status_code == 200 and r4.json()["instructor_id"] is None


# ---------------------------------------------------------------------------
# 5. Reschedule lifecycle: request → queue → approve (history kept) / reject
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reschedule_lifecycle(client, admin_user, student_a):
    u, s, e = student_a
    async with TestSessionLocal() as db:
        sess = ClassSession(enrollment_id=e.id, student_id=s.id, instructor_id=None,
                            scheduled_date=date.today() + timedelta(days=3),
                            scheduled_start=time(17, 0), scheduled_end=time(18, 0),
                            timezone="Asia/Kolkata", status="scheduled")
        db.add(sess)
        await db.commit()
        sid = sess.id

    tok = _tok(u)
    # student requests reschedule with a preferred slot
    flag = await client.post(f"/api/v1/sessions/{sid}/flag-reschedule",
        json={"reason": "Family event", "preferred_date": (date.today() + timedelta(days=5)).isoformat(),
              "preferred_start": "17:00", "preferred_end": "18:00"},
        headers={"Authorization": f"Bearer {tok}"})
    assert flag.status_code == 200
    assert flag.json()["preferred_date"] == (date.today() + timedelta(days=5)).isoformat()

    # student cannot execute the reschedule
    deny = await client.post(f"/api/v1/sessions/{sid}/reschedule",
        json={"new_date": "2027-01-01", "new_start": "10:00", "new_end": "11:00", "reason": "not permitted"},
        headers={"Authorization": f"Bearer {tok}"})
    assert deny.status_code == 403

    # instructor also cannot execute (final approval = admin)
    async with TestSessionLocal() as db:
        inst_user = await _mk_user(db, "wfinstr", "InstPass@123", UserRole.INSTRUCTOR)
        db.add(Instructor(user_id=inst_user.id, first_name="I", last_name="F", is_active=True))
        await db.commit()
    deny2 = await client.post(f"/api/v1/sessions/{sid}/reschedule",
        json={"new_date": "2027-01-01", "new_start": "10:00", "new_end": "11:00", "reason": "not permitted"},
        headers=auth(inst_user))
    assert deny2.status_code == 403

    # admin queue shows full details
    q = await client.get("/api/v1/sessions/reschedule-requests", headers=auth(admin_user))
    assert q.status_code == 200
    item = q.json()[0]
    assert item["student_cma"].startswith("CMA-2026-")
    assert item["reschedule_reason"] == "Family event"
    assert item["has_proposed_slot"] is True

    # approving: conflicting slot is refused (student has another class at that time?)
    # create a conflicting dated class for the same student at the proposed slot
    async with TestSessionLocal() as db:
        clash = ClassSession(enrollment_id=e.id, student_id=s.id, instructor_id=None,
                             scheduled_date=date.today() + timedelta(days=5),
                             scheduled_start=time(17, 30), scheduled_end=time(18, 30),
                             timezone="Asia/Kolkata", status="scheduled")
        db.add(clash)
        await db.commit()
    bad = await client.post(f"/api/v1/sessions/{sid}/reschedule",
        json={"new_date": (date.today() + timedelta(days=5)).isoformat(), "new_start": "17:00",
              "new_end": "18:00", "reason": "Approved"},
        headers=auth(admin_user))
    assert bad.status_code == 409   # conflicts detected, nothing overwritten

    # move clash away, then approve cleanly
    async with TestSessionLocal() as db:
        row = (await db.execute(select(ClassSession).where(ClassSession.id == clash.id))).scalar_one()
        row.scheduled_date = date.today() + timedelta(days=9)
        db.add(row)
        await db.commit()
    good = await client.post(f"/api/v1/sessions/{sid}/reschedule",
        json={"new_date": (date.today() + timedelta(days=5)).isoformat(), "new_start": "17:00",
              "new_end": "18:00", "reason": "Approved by academy"},
        headers=auth(admin_user))
    assert good.status_code == 201
    body = good.json()
    assert body["scheduled_date"] == (date.today() + timedelta(days=5)).isoformat()
    assert body["status"] == "scheduled"

    # original occurrence preserved with history (never deleted / recurring untouched)
    async with TestSessionLocal() as db:
        original = (await db.execute(select(ClassSession).where(ClassSession.id == sid))).scalar_one()
        assert original.status == "rescheduled"  # confirmed move (spec: Rescheduled state)
        assert original.replaces_session_id is None
    hist = await client.get(f"/api/v1/sessions/{sid}", headers=auth(admin_user))
    assert hist.status_code == 200
    assert len(hist.json().get("history", [])) >= 1

    # student notification exists
    notes = await client.get("/api/v1/portal/notifications", headers={"Authorization": f"Bearer {tok}"})
    assert notes.status_code == 200
    assert any("rescheduled" in (n.get("title") or "").lower() for n in notes.json())


@pytest.mark.asyncio
async def test_reschedule_reject_restores_original(client, admin_user, student_a):
    u, s, e = student_a
    async with TestSessionLocal() as db:
        sess = ClassSession(enrollment_id=e.id, student_id=s.id, instructor_id=None,
                            scheduled_date=date.today() + timedelta(days=4),
                            scheduled_start=time(10, 0), scheduled_end=time(11, 0),
                            timezone="Asia/Kolkata", status="scheduled")
        db.add(sess)
        await db.commit()
        sid = sess.id
    tok = _tok(u)
    await client.post(f"/api/v1/sessions/{sid}/flag-reschedule",
                      json={"reason": "Travel"}, headers={"Authorization": f"Bearer {tok}"})
    # reject requires reason
    assert (await client.post(f"/api/v1/sessions/{sid}/reject-reschedule",
                              json={}, headers=auth(admin_user))).status_code == 400
    rej = await client.post(f"/api/v1/sessions/{sid}/reject-reschedule",
                            json={"reason": "Faculty unavailable only this week"},
                            headers=auth(admin_user))
    assert rej.status_code == 200
    assert rej.json()["status"] == "scheduled"          # original slot restored
    # queue now empty
    q = await client.get("/api/v1/sessions/reschedule-requests", headers=auth(admin_user))
    assert q.json() == []
    # student notified of the decision
    notes = await client.get("/api/v1/portal/notifications", headers={"Authorization": f"Bearer {tok}"})
    assert any("declined" in (n.get("title") or "").lower() for n in notes.json())


# ---------------------------------------------------------------------------
# 6. Account management: create/edit/suspend/archive/delete
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_account_management_students_and_instructors(client, admin_user):
    h = auth(admin_user)
    # create student (temp PIN once, duplicates refused)
    res = await client.post("/api/v1/admin/students", json={
        "username": "CMA-8001", "first_name": "NewKid", "last_name": "R",
        "programme_id": "piano", "programme_name": "Piano", "fee_plan": "4_classes",
        "fee_amount": 4500}, headers=h)
    assert res.status_code == 201, res.text
    body = res.json()
    assert re.fullmatch(r"\d{4}", body["temp_pin"]) and body["must_change_pin"] is True
    sid = body["id"]
    dup = await client.post("/api/v1/admin/students", json={"username": "CMA-8001", "first_name": "X"}, headers=h)
    assert dup.status_code == 409

    # edit + suspend + reactivate + archive
    assert (await client.patch(f"/api/v1/admin/students/{sid}",
                               json={"phone": "999", "status": "suspended"}, headers=h)).status_code == 200
    assert (await client.patch(f"/api/v1/admin/students/{sid}",
                               json={"status": "active"}, headers=h)).status_code == 200
    arch = await client.patch(f"/api/v1/admin/students/{sid}", json={"status": "archived"}, headers=h)
    assert arch.status_code == 200 and arch.json()["status"] == "archived"

    # delete with history now performs a PERMANENT delete (archive stays optional):
    imp = await client.get(f"/api/v1/admin/students/{sid}/delete-impact", headers=h)
    assert imp.status_code == 200 and imp.json()["remove"]["enrollments"] >= 1
    deny = await client.delete(f"/api/v1/admin/students/{sid}", headers=h)
    assert deny.status_code == 200 and deny.json()["deleted"] is True
    assert deny.json()["removed"]["enrollments"] >= 1
    assert deny.json()["released"]["username"] == "CMA-8001"
    # released username is immediately reusable
    reuse = await client.post("/api/v1/admin/students",
                              json={"username": "CMA-8001", "first_name": "ReUsed"}, headers=h)
    assert reuse.status_code == 201

    # a clean student with no history CAN be deleted
    clean = await client.post("/api/v1/admin/students", json={"username": "CMA-8002", "first_name": "Clean"}, headers=h)
    clean_id = clean.json()["id"]
    ok_del = await client.delete(f"/api/v1/admin/students/{clean_id}", headers=h)
    assert ok_del.status_code == 200

    # instructors: create (temp PIN), edit, deactivate w/ impact ack, reactivate
    ires = await client.post("/api/v1/admin/instructors", json={
        "username": "wffac", "first_name": "Fac", "specializations": "Guitar"}, headers=h)
    assert ires.status_code == 201
    iid = ires.json()["id"]
    assert re.fullmatch(r"\d{4}", ires.json()["temp_pin"])
    assert (await client.patch(f"/api/v1/admin/instructors/{iid}",
                               json={"specializations": "Guitar, Vocals"}, headers=h)).status_code == 200
    # deactivate (no future classes → no ack needed)
    d = await client.patch(f"/api/v1/admin/instructors/{iid}", json={"is_active": False}, headers=h)
    assert d.status_code == 200 and d.json()["is_active"] is False
    assert (await client.patch(f"/api/v1/admin/instructors/{iid}", json={"is_active": True}, headers=h)).status_code == 200

    # public registration still cannot create accounts
    reg = await client.post("/api/v1/auth/register", json={
        "email": "pub@x.com", "username": "pubuser", "password": "Pw@123456", "role": "student"})
    assert reg.status_code == 403
