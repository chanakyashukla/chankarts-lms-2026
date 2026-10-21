"""
Monthly class scheduling: 4/8-class plans, instructor + student conflicts,
overlapping intervals, idempotent duplicate handling, completed-session
protection and unrelated-data safety.
"""
import uuid
from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_monthly_sched.db"
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
        u = User(id=uuid.uuid4(), username="schedadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Sched", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _mk_instructor(username: str) -> uuid.UUID:
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=username, hashed_password=get_password_hash("1234"),
                 role=UserRole.INSTRUCTOR, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        i = Instructor(id=uuid.uuid4(), user_id=u.id, first_name="Teach", last_name=username,
                       is_active=True)
        s.add(i)
        await s.commit()
        return i.id


async def _mk_student(username: str, instructor_id: uuid.UUID, fee_plan: str = "4_classes") -> tuple:
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=username, hashed_password=get_password_hash("1234"),
                 role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        st = Student(id=uuid.uuid4(), user_id=u.id, cma_registration_id=f"CMA-2026-{username[:6]}",
                     portal_slug=username, first_name=username.title(), last_name="S", status="active")
        s.add(st)
        await s.flush()
        e = Enrollment(id=uuid.uuid4(), student_id=st.id, programme_id="piano",
                       programme_name="Piano", instructor_id=instructor_id,
                       fee_plan=fee_plan, fee_amount=4500 if fee_plan == "4_classes" else 8000,
                       status="active")
        s.add(e)
        await s.commit()
        return st.id, e.id


async def _mk_session(student_id, enrollment_id, instructor_id, d, s_t, e_t, status="scheduled") -> uuid.UUID:
    async with TestSessionLocal() as s:
        row = ClassSession(id=uuid.uuid4(), enrollment_id=enrollment_id, student_id=student_id,
                           instructor_id=instructor_id, scheduled_date=d, scheduled_start=s_t,
                           scheduled_end=e_t, status=status)
        s.add(row)
        await s.commit()
        return row.id


def _slots(dates, start="17:00", end="18:00"):
    return [{"date": d, "start_time": start, "end_time": end} for d in dates]


MONTH = "2026-11"
DAYS = ["2026-11-02", "2026-11-05", "2026-11-09", "2026-11-12"]


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_four_class_plan_schedule_and_counts(client, admin_user):
    h = auth(admin_user)
    inst = await _mk_instructor("t4")
    sid, eid = await _mk_student("fourplan", inst)

    r = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                          json={"month": MONTH, "classes": _slots(DAYS)}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["scheduled"]) == 4
    assert body["classes_expected"] == 4 and body["remaining"] == 0 and body["month_total"] == 4

    g = await client.get(f"/api/v1/admin/students/{sid}/monthly-schedule?month={MONTH}", headers=h)
    gb = g.json()
    assert gb["plan"]["label"] == "4 classes / month"
    assert gb["counts"]["scheduled"] == 4 and gb["remaining"] == 0

    # re-saving the SAME slots is idempotent — no duplicates created
    r2 = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                           json={"month": MONTH, "classes": _slots(DAYS)}, headers=h)
    assert r2.status_code == 200
    assert r2.json()["skipped_duplicates"] == 4 and r2.json()["scheduled"] == [] and r2.json()["month_total"] == 4


@pytest.mark.asyncio
async def test_eight_class_plan_partial_and_full(client, admin_user):
    h = auth(admin_user)
    inst = await _mk_instructor("t8")
    sid, eid = await _mk_student("eightplan", inst, fee_plan="8_classes")

    first3 = _slots(DAYS[:3])
    r = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                          json={"month": MONTH, "classes": first3}, headers=h)
    assert r.status_code == 200 and r.json()["remaining"] == 5

    more = _slots(["2026-11-16", "2026-11-19", "2026-11-23", "2026-11-26", "2026-11-30"])
    r2 = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                           json={"month": MONTH, "classes": more}, headers=h)
    assert r2.status_code == 200 and r2.json()["month_total"] == 8 and r2.json()["remaining"] == 0


@pytest.mark.asyncio
async def test_instructor_conflict_blocks_with_specific_message(client, admin_user):
    h = auth(admin_user)
    inst = await _mk_instructor("tc")
    other_sid, other_eid = await _mk_student("otherbusy", inst)
    await _mk_session(other_sid, other_eid, inst, date(2026, 11, 12), time(17, 0), time(18, 0))
    sid, eid = await _mk_student("conflictst", inst)

    # overlapping interval (not identical start:17:30–18:30)
    r = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                          json={"month": MONTH, "classes": _slots(["2026-11-12"], "17:30", "18:30")},
                          headers=h)
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["conflicts"][0]["type"] == "instructor"
    assert "12 November" in detail["conflicts"][0]["message"]
    assert "5:30 PM" in detail["conflicts"][0]["message"]     # proposed slot,12-hour format
    # nothing was saved
    g = await client.get(f"/api/v1/admin/students/{sid}/monthly-schedule?month={MONTH}", headers=h)
    assert g.json()["sessions"] == []


@pytest.mark.asyncio
async def test_student_conflict_blocks(client, admin_user):
    h = auth(admin_user)
    inst = await _mk_instructor("tsc")
    sid, eid = await _mk_student("busykid", inst)
    await _mk_session(sid, eid, inst, date(2026, 11, 13), time(10, 0), time(11, 0))

    r = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                          json={"month": MONTH, "classes": _slots(["2026-11-13"], "10:30", "11:30")},
                          headers=h)
    assert r.status_code == 409
    c = r.json()["detail"]["conflicts"][0]
    assert c["type"] == "student" and "already has a class" in c["message"]


@pytest.mark.asyncio
async def test_weekly_timetable_conflict(client, admin_user):
    h = auth(admin_user)
    inst = await _mk_instructor("tw")
    sid, eid = await _mk_student("weeklykid", inst)
    # recurring Wednesday17:00–18:00 for this instructor (2026-11-11 is a Wednesday)
    async with TestSessionLocal() as s:
        s.add(ClassSchedule(id=uuid.uuid4(), enrollment_id=eid, instructor_id=inst,
                            day_of_week="wednesday", start_time=time(17, 0), end_time=time(18, 0),
                            frequency="weekly", is_active=True))
        await s.commit()
    r = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                          json={"month": MONTH, "classes": _slots(["2026-11-11"], "17:30", "18:30")},
                          headers=h)
    assert r.status_code == 409
    assert r.json()["detail"]["conflicts"][0]["type"] == "instructor_weekly"


@pytest.mark.asyncio
async def test_completed_sessions_untouched_and_unrelated_preserved(client, admin_user):
    h = auth(admin_user)
    inst = await _mk_instructor("tp")
    sid, eid = await _mk_student("keephist", inst)
    done_id = await _mk_session(sid, eid, inst, date(2026, 11, 5), time(10, 0), time(11, 0), status="completed")
    # unrelated student session that must survive
    sid2, eid2 = await _mk_student("unrelatedx", inst)
    other_id = await _mk_session(sid2, eid2, inst, date(2026, 11, 20), time(9, 0), time(10, 0))

    r = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                          json={"month": MONTH, "classes": _slots(["2026-11-12", "2026-11-19"])},
                          headers=h)
    assert r.status_code == 200 and len(r.json()["scheduled"]) == 2

    async with TestSessionLocal() as s:
        done = (await s.execute(select(ClassSession).where(ClassSession.id == done_id))).scalar_one()
        assert done.status == "completed" and done.scheduled_start == time(10, 0)
        other = (await s.execute(select(ClassSession).where(ClassSession.id == other_id))).scalar_one()
        assert other.student_id == sid2 and other.status == "scheduled"
        # completed class counted in the month
    g = await client.get(f"/api/v1/admin/students/{sid}/monthly-schedule?month={MONTH}", headers=h)
    gb = g.json()
    assert gb["counts"]["completed"] == 1 and gb["scheduled_total"] == 3


@pytest.mark.asyncio
async def test_validation_errors(client, admin_user):
    h = auth(admin_user)
    inst = await _mk_instructor("tv")
    sid, eid = await _mk_student("valkid", inst)
    # outside month
    r = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                          json={"month": MONTH, "classes": _slots(["2026-12-01"])}, headers=h)
    assert r.status_code == 400 and "outside the selected month" in r.json()["detail"]
    # end before start
    r = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                          json={"month": MONTH, "classes": _slots(["2026-11-02"], "18:00", "17:00")}, headers=h)
    assert r.status_code == 400 and "End time must be after" in r.json()["detail"]
    # duplicate inside one request
    r = await client.post(f"/api/v1/admin/students/{sid}/monthly-schedule",
                          json={"month": MONTH, "classes": _slots(["2026-11-02"]) + _slots(["2026-11-02"])},
                          headers=h)
    assert r.status_code == 400 and "Duplicate slot" in r.json()["detail"]
    # student without enrolment
    sid2, _ = await _mk_student("noenrl", inst)
    async with TestSessionLocal() as s:
        e = (await s.execute(select(Enrollment).where(Enrollment.student_id == sid2))).scalar_one()
        e.status = "completed"
        await s.commit()
    r = await client.post(f"/api/v1/admin/students/{sid2}/monthly-schedule",
                          json={"month": MONTH, "classes": _slots(["2026-11-02"])}, headers=h)
    assert r.status_code == 400 and "enrolment" in r.json()["detail"].lower()
