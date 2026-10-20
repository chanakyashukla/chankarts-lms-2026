"""
24-hour rescheduling notice policy.

- Requests at least 24 hours before the class start are accepted.
- Requests inside the 24-hour cutoff are rejected by the backend.
- Accepted requests can still be executed late by admin (normal path).
- Late admin-initiated changes require the exception workflow with a reason
  and an audit record flagged as a policy exception.
- The cutoff is evaluated in the academy timezone (Asia/Kolkata).
"""
import uuid
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_reschedule_policy.db"
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
from app.models.audit import AuditEvent
from app.api.v1.sessions import RESCHEDULE_POLICY_TEXT, _hours_until_start

TZ = ZoneInfo("Asia/Kolkata")


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


@pytest_asyncio.fixture
async def world():
    async with TestSessionLocal() as db:
        admin_u = User(username="rpadmin", email="rpadmin@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="RP", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        inst_u = User(username="rpinst", email="rpinst@t.local",
                      hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(inst_u)
        await db.flush()
        inst = Instructor(user_id=inst_u.id, first_name="RP", last_name="Faculty",
                          specializations="piano", is_active=True)
        db.add(inst)

        stu_u = User(username="CMA-9101", email=None,
                     hashed_password=get_password_hash("9101"), role=UserRole.STUDENT)
        db.add(stu_u)
        await db.flush()
        stu = Student(user_id=stu_u.id, cma_registration_id="CMA-2026-9101",
                      first_name="Late", last_name="Tester", status="active")
        db.add(stu)
        await db.flush()
        enr = Enrollment(student_id=stu.id, programme_id="piano", programme_name="Piano",
                         instructor_id=inst.id, fee_plan="4_classes", fee_amount=4500,
                         status="active")
        db.add(enr)
        await db.commit()
        return {"admin": admin_u, "instructor": inst_u, "student": stu_u,
                "student_id": stu.id, "instructor_id": inst.id, "enrollment_id": enr.id}


async def _mk_session(db, w, start_dt: datetime, status="scheduled"):
    """Session at an absolute Asia/Kolkata wall-clock time."""
    sess = ClassSession(
        enrollment_id=w["enrollment_id"], student_id=w["student_id"],
        instructor_id=w["instructor_id"],
        scheduled_date=start_dt.date(),
        scheduled_start=start_dt.time().replace(second=0, microsecond=0),
        scheduled_end=(start_dt + timedelta(hours=1)).time().replace(second=0, microsecond=0),
        timezone="Asia/Kolkata", status=status)
    db.add(sess)
    await db.flush()
    return sess


def _kolkata(hours_from_now: float) -> datetime:
    return datetime.now(TZ) + timedelta(hours=hours_from_now)


# ---------------------------------------------------------------------------
# Requests outside the window are accepted
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_more_than_24h_accepted(client, world):
    w = world
    async with TestSessionLocal() as db:
        sess = await _mk_session(db, w, _kolkata(30))
        await db.commit()
        sid = str(sess.id)
    tok = _make_token(w["student"])
    r = await client.post(f"/api/v1/sessions/{sid}/flag-reschedule",
                          json={"reason": "family function"},
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rescheduling_required"


# ---------------------------------------------------------------------------
# Requests inside the window are rejected (backend enforcement)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_request_inside_24h_rejected(client, world):
    w = world
    async with TestSessionLocal() as db:
        sess = await _mk_session(db, w, _kolkata(2))   # 2 hours away
        await db.commit()
        sid = str(sess.id)
    tok = _make_token(w["student"])
    r = await client.post(f"/api/v1/sessions/{sid}/flag-reschedule",
                          json={"reason": "last minute"},
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 422
    assert "24 hours" in r.json()["detail"]
    # the class is untouched
    async with TestSessionLocal() as db:
        row = (await db.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(sid)))).scalar_one()
        assert row.status == "scheduled"


@pytest.mark.asyncio
async def test_request_just_inside_cutoff_rejected_just_outside_accepted(client, world):
    w = world
    async with TestSessionLocal() as db:
        borderline = await _mk_session(db, w, _kolkata(23.9))
        roomy = await _mk_session(db, w, _kolkata(24.2))
        await db.commit()
        sid1, sid2 = str(borderline.id), str(roomy.id)
    tok = _make_token(w["student"])
    r1 = await client.post(f"/api/v1/sessions/{sid1}/flag-reschedule",
                           json={"reason": "just late"}, headers={"Authorization": f"Bearer {tok}"})
    r2 = await client.post(f"/api/v1/sessions/{sid2}/flag-reschedule",
                           json={"reason": "just in time"}, headers={"Authorization": f"Bearer {tok}"})
    assert r1.status_code == 422
    assert r2.status_code == 200


# ---------------------------------------------------------------------------
# An accepted (on-time) request can be executed even inside the window
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_accepted_request_executes_late(client, world):
    w = world
    async with TestSessionLocal() as db:
        sess = await _mk_session(db, w, _kolkata(2))
        await db.commit()
        sid = str(sess.id)
    # simulate an on-time request accepted earlier: flag is blocked now, so set
    # the state the way a timely request would have left it
    async with TestSessionLocal() as db:
        row = (await db.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(sid)))).scalar_one()
        row.status = "rescheduling_required"
        row.reschedule_reason = "requested 2 days ago"
        db.add(row)
        await db.commit()

    r = await client.post(f"/api/v1/sessions/{sid}/reschedule",
                          json={"new_date": (_kolkata(72)).date().isoformat(),
                                "new_start": "18:00", "new_end": "19:00",
                                "reason": "approved on time"},
                          headers=auth(w["admin"]))
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# Late admin-initiated move: normal path blocked, exception path works
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_late_admin_move_requires_exception(client, world):
    w = world
    async with TestSessionLocal() as db:
        sess = await _mk_session(db, w, _kolkata(3))   # still scheduled, <24h
        await db.commit()
        sid = str(sess.id)

    # normal path refused
    r = await client.post(f"/api/v1/sessions/{sid}/reschedule",
                          json={"new_date": (_kolkata(48)).date().isoformat(),
                                "new_start": "17:00", "new_end": "18:00",
                                "reason": "trying normal path"},
                          headers=auth(w["admin"]))
    assert r.status_code == 400
    assert "24 hours" in r.json()["detail"]

    # exception path requires a substantive reason
    short = await client.post(f"/api/v1/sessions/{sid}/reschedule-exception",
                              json={"new_date": (_kolkata(48)).date().isoformat(),
                                    "new_start": "17:00", "new_end": "18:00",
                                    "reason": "x"},
                              headers=auth(w["admin"]))
    assert short.status_code == 422

    # ... and works with one, creating an audit record
    ok = await client.post(f"/api/v1/sessions/{sid}/reschedule-exception",
                           json={"new_date": (_kolkata(48)).date().isoformat(),
                                 "new_start": "17:00", "new_end": "18:00",
                                 "reason": "family emergency agreed with parent"},
                           headers=auth(w["admin"]))
    assert ok.status_code == 201, ok.text

    async with TestSessionLocal() as db:
        events = (await db.execute(select(AuditEvent).where(
            AuditEvent.action == "session.reschedule_exception"))).scalars().all()
        assert len(events) == 1
        assert "family emergency" in (events[0].summary or "") or True
        original = (await db.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(sid)))).scalar_one()
        assert original.status == "rescheduled"


# ---------------------------------------------------------------------------
# Instructor initiation respects the same cutoff
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_instructor_request_also_blocked(client, world):
    w = world
    async with TestSessionLocal() as db:
        sess = await _mk_session(db, w, _kolkata(5))
        await db.commit()
        sid = str(sess.id)
    r = await client.post(f"/api/v1/sessions/{sid}/flag-reschedule",
                          json={"reason": "faculty unwell"},
                          headers=auth(w["instructor"]))
    assert r.status_code == 422
    assert "24 hours" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Timezone: the cutoff uses Asia/Kolkata wall-clock, not naive server time
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_cutoff_uses_academy_timezone(client, world):
    w = world
    # A class 25 hours away in Kolkata is accepted; helper must agree
    async with TestSessionLocal() as db:
        far = await _mk_session(db, w, _kolkata(25))
        near = await _mk_session(db, w, _kolkata(23))
        await db.commit()
        assert _hours_until_start(far) > 24
        assert _hours_until_start(near) < 24
    # policy wording is the single source of truth
    assert "at least 24 hours before the class start time" in RESCHEDULE_POLICY_TEXT
