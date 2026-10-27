"""
Fixed weekly timetable slot deletion: single-row removal, optional future
session cancellation, preservation of history/pending reschedules/other slots,
inactive-instructor rows, monthly counts and persistence.
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_slot_delete.db"
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
from app.models.attendance import Attendance


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
        u = User(id=uuid.uuid4(), username="slotadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Slot", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _world(active=True):
    async with TestSessionLocal() as s:
        iu = User(id=uuid.uuid4(), username=f"si{uuid.uuid4().hex[:6]}",
                  hashed_password=get_password_hash("1"), role=UserRole.INSTRUCTOR,
                  is_active=active, must_change_pin=False)
        s.add(iu); await s.flush()
        ins = Instructor(id=uuid.uuid4(), user_id=iu.id, first_name="Slot", last_name="Ins",
                         is_active=active)
        s.add(ins)
        def stu(name):
            return None
        u1 = User(id=uuid.uuid4(), username="slotstu", hashed_password=get_password_hash("1"),
                  role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(u1); await s.flush()
        st = Student(id=uuid.uuid4(), user_id=u1.id, cma_registration_id="CMA-2026-SLOT",
                     portal_slug="slotstu", first_name="Slot", last_name="Kid", status="active")
        s.add(st); await s.flush()
        e = Enrollment(id=uuid.uuid4(), student_id=st.id, programme_id="piano",
                       programme_name="Piano", instructor_id=ins.id, fee_plan="4_classes",
                       fee_amount=4500, status="active")
        s.add(e); await s.flush()
        # two weekly rows: Monday and Wednesday
        mon = ClassSchedule(id=uuid.uuid4(), enrollment_id=e.id, instructor_id=ins.id,
                            day_of_week="monday", start_time=time(17, 0), end_time=time(18, 0),
                            frequency="weekly", is_active=True)
        wed = ClassSchedule(id=uuid.uuid4(), enrollment_id=e.id, instructor_id=ins.id,
                            day_of_week="wednesday", start_time=time(17, 0), end_time=time(18, 0),
                            frequency="weekly", is_active=True)
        s.add_all([mon, wed])
        # unrelated student with a Monday17:00 session (must survive)
        u2 = User(id=uuid.uuid4(), username="slotother", hashed_password=get_password_hash("1"),
                  role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(u2); await s.flush()
        st2 = Student(id=uuid.uuid4(), user_id=u2.id, cma_registration_id="CMA-2026-OTHR",
                      portal_slug="slotother", first_name="Other", last_name="Kid", status="active")
        s.add(st2); await s.flush()
        e2 = Enrollment(id=uuid.uuid4(), student_id=st2.id, programme_id="guitar",
                        programme_name="Guitar", instructor_id=ins.id, status="active")
        s.add(e2)
        await s.commit()
        return {"instructor": ins.id, "student": st.id, "enrollment": e.id,
                "mon": mon.id, "wed": wed.id, "other_enrollment": e2.id, "other_student": st2.id}


async def _add(student, enrollment, instructor, d, st_, en_, status="scheduled"):
    async with TestSessionLocal() as s:
        row = ClassSession(id=uuid.uuid4(), enrollment_id=enrollment, student_id=student,
                           instructor_id=instructor, scheduled_date=d, scheduled_start=st_,
                           scheduled_end=en_, status=status)
        s.add(row); await s.commit()
        return row.id



def _future_weekday(weekday: int, weeks: int = 0) -> date:
    """First strictly-future date on the given weekday (Mon=0), +weeks."""
    d = date.today() + timedelta(days=1)
    while d.weekday() != weekday or d <= date.today():
        d += timedelta(days=1)
    return d + timedelta(days=7 * weeks)

# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_impact_reports_future_and_history(client, admin_user):
    h = auth(admin_user)
    w = await _world()
    done = await _add(w["student"], w["enrollment"], w["instructor"], date.today() - timedelta(days=8), time(17, 0), time(18, 0), "completed")
    fut_date = _future_weekday(0)   # next Monday — matches the Monday slot
    fut = await _add(w["student"], w["enrollment"], w["instructor"], fut_date, time(17, 0), time(18, 0))
    r = await client.get(f"/api/v1/admin/schedules/{w['mon']}/delete-impact", headers=h)
    assert r.status_code == 200, r.text
    imp = r.json()
    assert imp["schedule"]["day_of_week"] == "monday"
    assert imp["schedule"]["student"]["full_name"] == "Slot Kid"
    assert imp["schedule"]["instructor_name"] == "Slot Ins"
    assert [f["date"] for f in imp["future_sessions"]] == [fut_date.isoformat()]
    assert imp["historical_count"] == 1
    assert imp["monthly_classes_expected"] == 4


@pytest.mark.asyncio
async def test_delete_slot_with_future_cancellation(client, admin_user):
    h = auth(admin_user)
    w = await _world()
    done = await _add(w["student"], w["enrollment"], w["instructor"], date.today() - timedelta(days=8), time(17, 0), time(18, 0), "completed")
    m1 = _future_weekday(0)            # Monday +0
    m2 = _future_weekday(0, weeks=1)   # Monday +1 week
    f1 = await _add(w["student"], w["enrollment"], w["instructor"], m1, time(17, 0), time(18, 0))
    f2 = await _add(w["student"], w["enrollment"], w["instructor"], m2, time(17, 0), time(18, 0))
    pend = await _add(w["student"], w["enrollment"], w["instructor"], _future_weekday(0, weeks=2), time(17, 0), time(18, 0), "rescheduling_required")
    wed_f = await _add(w["student"], w["enrollment"], w["instructor"], _future_weekday(2), time(17, 0), time(18, 0))
    other = await _add(w["other_student"], w["other_enrollment"], w["instructor"], m1, time(17, 0), time(18, 0))

    r = await client.delete(f"/api/v1/admin/schedules/{w['mon']}?cancel_future=true", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True and body["cancelled_future"] == 2
    assert body["rescheduling_pending_kept"] == 1

    async with TestSessionLocal() as s:
        # only the Monday row is gone; Wednesday intact
        mon = (await s.execute(select(ClassSchedule).where(ClassSchedule.id == uuid.UUID(str(w["mon"]))))).scalar_one_or_none()
        wed = (await s.execute(select(ClassSchedule).where(ClassSchedule.id == uuid.UUID(str(w["wed"]))))).scalar_one_or_none()
        assert mon is None and wed is not None
        # matching futures cancelled (NOT deleted — no orphans)
        for rid in (f1, f2):
            row = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(str(rid))))).scalar_one()
            assert row.status == "cancelled"
        # completed + pending reschedule + other rows untouched
        assert (await s.execute(select(ClassSession.status).where(ClassSession.id == uuid.UUID(str(done))))).scalar() == "completed"
        assert (await s.execute(select(ClassSession.status).where(ClassSession.id == uuid.UUID(str(pend))))).scalar() == "rescheduling_required"
        assert (await s.execute(select(ClassSession.status).where(ClassSession.id == uuid.UUID(str(wed_f))))).scalar() == "scheduled"
        assert (await s.execute(select(ClassSession.status).where(ClassSession.id == uuid.UUID(str(other))))).scalar() == "scheduled"
        # total session rows preserved (cancelled in place)
        total = (await s.execute(select(func.count(ClassSession.id)))).scalar()
        assert total == 6
        # audit recorded
        from app.models.audit import AuditEvent
        ev = (await s.execute(select(AuditEvent).where(AuditEvent.action == "schedule.slot_deleted"))).scalars().all()
        assert ev

    # page refresh equivalent: impact now404s, list no longer shows the row
    r = await client.get(f"/api/v1/admin/schedules/{w['mon']}/delete-impact", headers=h)
    assert r.status_code == 404
    lst = (await client.get("/api/v1/admin/schedules", headers=h)).json()
    ids = {x["id"] for x in lst["schedules"]}
    assert str(w["mon"]) not in ids and str(w["wed"]) in ids


@pytest.mark.asyncio
async def test_delete_slot_keeps_future_by_default(client, admin_user):
    h = auth(admin_user)
    w = await _world()
    fut = await _add(w["student"], w["enrollment"], w["instructor"], _future_weekday(0), time(17, 0), time(18, 0))
    r = await client.delete(f"/api/v1/admin/schedules/{w['mon']}", headers=h)
    assert r.status_code == 200 and r.json()["cancelled_future"] == 0
    async with TestSessionLocal() as s:
        row = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(str(fut))))).scalar_one()
        assert row.status == "scheduled"          # kept as an explicit one-off


@pytest.mark.asyncio
async def test_delete_slot_with_inactive_instructor(client, admin_user):
    h = auth(admin_user)
    w = await _world(active=False)                # the screenshot scenario
    r = await client.get(f"/api/v1/admin/schedules/{w['mon']}/delete-impact", headers=h)
    assert r.status_code == 200
    assert r.json()["schedule"]["instructor_active"] is False
    # deletable without reactivating the instructor or reassigning
    r = await client.delete(f"/api/v1/admin/schedules/{w['mon']}?cancel_future=true", headers=h)
    assert r.status_code == 200
    async with TestSessionLocal() as s:
        ins = (await s.execute(select(Instructor).where(Instructor.id == uuid.UUID(str(w["instructor"]))))).scalar_one()
        assert ins.is_active is False            # instructor untouched
        mon = (await s.execute(select(ClassSchedule).where(ClassSchedule.id == uuid.UUID(str(w["mon"]))))).scalar_one_or_none()
        assert mon is None


@pytest.mark.asyncio
async def test_monthly_counts_stay_correct_after_cancel(client, admin_user):
    h = auth(admin_user)
    w = await _world()
    fut_date = _future_weekday(0)
    mon_of = fut_date.strftime("%Y-%m")
    await _add(w["student"], w["enrollment"], w["instructor"], fut_date, time(17, 0), time(18, 0))
    m = await client.get(f"/api/v1/admin/students/{w['student']}/monthly-schedule?month={mon_of}", headers=h)
    assert m.json()["scheduled_total"] == 1
    await client.delete(f"/api/v1/admin/schedules/{w['mon']}?cancel_future=true", headers=h)
    m = await client.get(f"/api/v1/admin/students/{w['student']}/monthly-schedule?month={mon_of}", headers=h)
    body = m.json()
    assert body["scheduled_total"] == 0            # cancelled excluded from scheduled
    assert body["counts"]["cancelled"] == 1
    assert body["plan"]["classes_expected"] == 4   # entitlement unchanged
