"""
Recurring schedule changes: Saturday→Sunday effective next month, holiday
time changes, alternatives, instructor/student overlap blocking, travel-time
buffer (insufficient vs unknown), future-effective application without touching
history, no duplicate sessions and preserved monthly entitlement.
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_recurring_change.db"
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
        u = User(id=uuid.uuid4(), username="schadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Sch", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _mk_world(buffer=None, weekday="saturday", start=time(16, 30), end=time(17, 30),
                    student_name="changer", instructor_name="Changer") -> dict:
    async with TestSessionLocal() as s:
        iu = User(id=uuid.uuid4(), username=f"i{uuid.uuid4().hex[:6]}",
                  hashed_password=get_password_hash("1234"), role=UserRole.INSTRUCTOR,
                  is_active=True, must_change_pin=False)
        s.add(iu)
        await s.flush()
        ins = Instructor(id=uuid.uuid4(), user_id=iu.id, first_name=instructor_name,
                         last_name="T", is_active=True, travel_buffer_minutes=buffer)
        s.add(ins)
        su = User(id=uuid.uuid4(), username=f"s{uuid.uuid4().hex[:6]}",
                  hashed_password=get_password_hash("1234"), role=UserRole.STUDENT,
                  is_active=True, must_change_pin=False)
        s.add(su)
        await s.flush()
        stu = Student(id=uuid.uuid4(), user_id=su.id, cma_registration_id=f"CMA-2026-{uuid.uuid4().hex[:4].upper()}",
                      portal_slug=f"stu-{uuid.uuid4().hex[:6]}", first_name=student_name,
                      last_name="Kid", status="active")
        s.add(stu)
        await s.flush()
        enr = Enrollment(id=uuid.uuid4(), student_id=stu.id, programme_id="piano",
                         programme_name="Piano", instructor_id=ins.id,
                         fee_plan="4_classes", fee_amount=4500, status="active")
        s.add(enr)
        await s.flush()
        sch = ClassSchedule(id=uuid.uuid4(), enrollment_id=enr.id, instructor_id=ins.id,
                            day_of_week=weekday, start_time=start, end_time=end,
                            frequency="weekly", is_active=True, location="Studio A")
        s.add(sch)
        await s.commit()
        return {"instructor": ins.id, "student": stu.id, "enrollment": enr.id,
                "schedule": sch.id, "user": su.id}


async def _add_session(student_id, enrollment_id, instructor_id, d, st, en,
                       status="scheduled", location=None, is_online=False) -> uuid.UUID:
    async with TestSessionLocal() as s:
        row = ClassSession(id=uuid.uuid4(), enrollment_id=enrollment_id, student_id=student_id,
                           instructor_id=instructor_id, scheduled_date=d, scheduled_start=st,
                           scheduled_end=en, status=status, location=location, is_online=is_online)
        s.add(row)
        await s.commit()
        return row.id


def _change(new_day="sunday", start="16:30", end="17:30", eff="2026-11-01",
            confirm=False, ack=False, **extra):
    body = {"new_days": [{"day": new_day, "start_time": start, "end_time": end}],
            "effective_date": eff, "confirm": confirm,
            "acknowledge_travel_unknown": ack}
    body.update(extra)
    return body


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_saturday_to_sunday_effective_next_month(client, admin_user):
    h = auth(admin_user)
    w = await _mk_world()
    done = await _add_session(w["student"], w["enrollment"], w["instructor"],
                              date(2026, 10, 24), time(16, 30), time(17, 30), status="completed")
    fut = await _add_session(w["student"], w["enrollment"], w["instructor"],
                             date(2026, 11, 7), time(16, 30), time(17, 30))   # a Saturday

    # preview: future Saturday maps to Sunday2026-11-08, completed untouched
    p = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(confirm=False), headers=h)
    assert p.status_code == 200, p.text
    prev = p.json()
    assert prev["proposed"][0]["day"] == "sunday"
    assert prev["proposed"][0]["first_occurrence"] == "2026-11-01"
    aff = {a["session_id"]: a for a in prev["affected_sessions"]}
    assert str(fut) in aff and aff[str(fut)]["new_date"] == "2026-11-08"
    assert str(done) not in aff                       # completed excluded
    assert not prev["hard_conflicts"]

    # apply
    a = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(confirm=True), headers=h)
    assert a.status_code == 200, a.text
    body = a.json()
    assert body["applied"] is True and len(body["sessions_moved"]) == 1

    async with TestSessionLocal() as s:
        old_row = (await s.execute(select(ClassSchedule).where(ClassSchedule.id == uuid.UUID(str(w["schedule"]))))).scalar_one()
        assert old_row.is_active is False and old_row.end_date == date(2026, 10, 31)
        new_rows = (await s.execute(select(ClassSchedule).where(
            ClassSchedule.enrollment_id == uuid.UUID(str(w["enrollment"])),
            ClassSchedule.is_active.is_(True)))).scalars().all()
        assert len(new_rows) == 1 and new_rows[0].day_of_week == "sunday"
        assert new_rows[0].start_date == date(2026, 11, 1)
        moved = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(str(fut))))).scalar_one()
        assert moved.scheduled_date == date(2026, 11, 8) and moved.scheduled_start == time(16, 30)
        completed = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(str(done))))).scalar_one()
        assert completed.status == "completed" and completed.scheduled_date == date(2026, 10, 24)
        # no duplicates: total sessions unchanged
        total = (await s.execute(select(func.count(ClassSession.id)).where(
            ClassSession.student_id == uuid.UUID(str(w["student"]))))).scalar()
        assert total == 2
    # audit logged
    from app.models.audit import AuditEvent
    async with TestSessionLocal() as s:
        ev = (await s.execute(select(AuditEvent).where(
            AuditEvent.action == "student.recurring_schedule_changed"))).scalars().all()
        assert ev


@pytest.mark.asyncio
async def test_holiday_time_change_same_day(client, admin_user):
    h = auth(admin_user)
    w = await _mk_world(weekday="thursday", start=time(16, 30), end=time(17, 30))
    fut = await _add_session(w["student"], w["enrollment"], w["instructor"],
                             date(2026, 11, 5), time(16, 30), time(17, 30))  # a Thursday
    a = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(new_day="thursday", start="13:00", end="14:00",
                                       eff="2026-11-01", confirm=True, ack=True), headers=h)
    assert a.status_code == 200, a.text
    async with TestSessionLocal() as s:
        moved = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(str(fut))))).scalar_one()
        assert moved.scheduled_date == date(2026, 11, 5)     # same day, holiday time
        assert moved.scheduled_start == time(13, 0)


@pytest.mark.asyncio
async def test_alternatives_offered_when_slot_occupied(client, admin_user):
    h = auth(admin_user)
    w = await _mk_world()
    # instructor teaches another student's class at the proposed Sunday first occurrence17:00
    async with TestSessionLocal() as s:
        su = User(id=uuid.uuid4(), username="busybusy", hashed_password=get_password_hash("1"),
                  role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(su); await s.flush()
        other = Student(id=uuid.uuid4(), user_id=su.id, cma_registration_id="CMA-2026-BUSY",
                        portal_slug="busy", first_name="Busy", last_name="Kid", status="active")
        s.add(other); await s.flush()
        oe = Enrollment(id=uuid.uuid4(), student_id=other.id, programme_id="guitar",
                        programme_name="Guitar", instructor_id=w["instructor"], status="active")
        s.add(oe); await s.flush()
        s.add(ClassSession(id=uuid.uuid4(), enrollment_id=oe.id, student_id=other.id,
                           instructor_id=w["instructor"], scheduled_date=date(2026, 11, 1),
                           scheduled_start=time(16, 30), scheduled_end=time(17, 30),
                           status="scheduled"))
        await s.commit()
    p = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(start="16:30", end="17:30", eff="2026-11-01"), headers=h)
    assert p.status_code == 200
    prop = p.json()["proposed"][0]
    assert prop["status"] == "conflict"
    assert "already has a class" in prop["message"]
    assert prop["alternatives"], "expected alternative slots"
    assert all(a["start"] != "16:30" for a in prop["alternatives"])
    # confirmation is blocked while conflicts exist
    a = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(start="16:30", end="17:30", eff="2026-11-01", confirm=True), headers=h)
    assert a.status_code == 409
    assert a.json()["detail"]["conflicts"]


@pytest.mark.asyncio
async def test_student_overlap_blocks_move(client, admin_user):
    h = auth(admin_user)
    w = await _mk_world()
    fut = await _add_session(w["student"], w["enrollment"], w["instructor"],
                             date(2026, 11, 7), time(16, 30), time(17, 30))
    # the student already has another commitment on the target Sunday16:30
    await _add_session(w["student"], w["enrollment"], w["instructor"],
                       date(2026, 11, 8), time(16, 30), time(17, 30))
    a = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(confirm=True), headers=h)
    assert a.status_code == 409
    conflicts = a.json()["detail"]["conflicts"]
    assert any(c["type"] in ("student", "duplicate_target") for c in conflicts)
    # nothing moved
    async with TestSessionLocal() as s:
        sess = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(str(fut))))).scalar_one()
        assert sess.scheduled_date == date(2026, 11, 7)


@pytest.mark.asyncio
async def test_travel_insufficient_blocks_save(client, admin_user):
    h = auth(admin_user)
    w = await _mk_world(buffer=45)   #45-minute travel buffer
    # instructor's previous OFFLINE class ends17:00 with a location, on the first occurrence
    await _add_session(w["student"], w["enrollment"], w["instructor"],
                       date(2026, 11, 1), time(16, 30), time(17, 0), location="Studio A")
    p = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(start="17:15", end="18:15", eff="2026-11-01"), headers=h)
    # preview marks travel problem for the pattern (only15 minutes gap <45)
    prop = p.json()["proposed"][0]
    assert prop["status"] == "travel_insufficient" or prop["status"] == "conflict"
    a = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(start="17:15", end="18:15", eff="2026-11-01",
                                       confirm=True, ack=True), headers=h)
    assert a.status_code == 409                     # acknowledgement never overrides a hard conflict
    detail = a.json()["detail"]
    assert detail["conflicts"] or detail.get("warnings")


@pytest.mark.asyncio
async def test_travel_unknown_requires_acknowledgement(client, admin_user):
    h = auth(admin_user)
    w = await _mk_world(buffer=None)                # no travel buffer configured
    # neighbour offline class (locations missing → cannot confirm travel)
    await _add_session(w["student"], w["enrollment"], w["instructor"],
                       date(2026, 11, 1), time(16, 30), time(17, 0))
    p = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(start="17:15", end="18:15", eff="2026-11-01"), headers=h)
    assert p.status_code == 200
    prev = p.json()
    assert prev["requires_travel_ack"] is True
    assert prev["warnings"]
    # save without acknowledgement → refused with explicit flag
    a = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(start="17:15", end="18:15", eff="2026-11-01", confirm=True),
                          headers=h)
    assert a.status_code == 409
    assert a.json()["detail"].get("requires_travel_ack") is True
    # with acknowledgement → applied
    a2 = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                           json=_change(start="17:15", end="18:15", eff="2026-11-01",
                                        confirm=True, ack=True), headers=h)
    assert a2.status_code == 200, a2.text


@pytest.mark.asyncio
async def test_online_class_skips_travel_and_unrelated_students_untouched(client, admin_user):
    h = auth(admin_user)
    w = await _mk_world(buffer=None)
    # online template: schedule row online → travel checks skipped
    async with TestSessionLocal() as s:
        sch = (await s.execute(select(ClassSchedule).where(ClassSchedule.id == uuid.UUID(str(w["schedule"]))))).scalar_one()
        sch.is_online = True
        s.add(sch); await s.commit()
    # unrelated student with a fixed session must survive the change
    other = await _mk_world(student_name="bystander", instructor_name="Bystander")
    keep = await _add_session(other["student"], other["enrollment"], other["instructor"],
                              date(2026, 11, 7), time(10, 0), time(11, 0))
    a = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(eff="2026-11-01", confirm=True, ack=True), headers=h)
    assert a.status_code == 200, a.text
    assert not a.json()["warnings"]        # online → travel not required
    async with TestSessionLocal() as s:
        bystander = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(str(keep))))).scalar_one()
        assert bystander.scheduled_date == date(2026, 11, 7) and bystander.status == "scheduled"


@pytest.mark.asyncio
async def test_entitlement_and_availability_endpoint(client, admin_user):
    h = auth(admin_user)
    w = await _mk_world()
    # monthly entitlement unchanged by the change
    a = await client.post(f"/api/v1/admin/students/{w['student']}/recurring-schedule-change",
                          json=_change(confirm=True), headers=h)
    assert a.status_code == 200
    m = await client.get(f"/api/v1/admin/students/{w['student']}/monthly-schedule?month=2026-11",
                         headers=h)
    assert m.status_code == 200
    assert m.json()["plan"]["classes_expected"] == 4
    # availability endpoint: free slot → available with alternatives absent
    r = await client.get(
        f"/api/v1/admin/instructors/{w['instructor']}/slot-availability"
        f"?date=2026-11-04&start_time=10:00&end_time=11:00", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "available"
    # occupied slot → conflict + alternatives
    await _add_session(w["student"], w["enrollment"], w["instructor"],
                       date(2026, 11, 4), time(10, 0), time(11, 0))
    r2 = await client.get(
        f"/api/v1/admin/instructors/{w['instructor']}/slot-availability"
        f"?date=2026-11-04&start_time=10:00&end_time=11:00", headers=h)
    b = r2.json()
    assert b["status"] == "conflict" and b["alternatives"]
