"""
Permanent instructor deletion: impact reporting, dependency resolution
(unassign/cancel/reassign), history preservation, rollback safety, released
login, and post-deletion unassignability — plus deactivate/reactivate keeping
the profile intact.
"""
import uuid
from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_instr_delete.db"
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
        u = User(id=uuid.uuid4(), username="idmadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Idm", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _mk_instructor(username: str, active=True):
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=username, hashed_password=get_password_hash("4321"),
                 role=UserRole.INSTRUCTOR, is_active=active, must_change_pin=False)
        s.add(u); await s.flush()
        i = Instructor(id=uuid.uuid4(), user_id=u.id, first_name=username.title(), last_name="T",
                       is_active=active)
        s.add(i); await s.commit()
        return str(i.id), str(u.id)


async def _mk_world(ins_id: str):
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=f"idmstu{uuid.uuid4().hex[:6]}",
                 hashed_password=get_password_hash("1"),
                 role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(u); await s.flush()
        st = Student(id=uuid.uuid4(), user_id=u.id, cma_registration_id=f"CMA-2026-{uuid.uuid4().hex[:5].upper()}",
                     portal_slug=f"p{uuid.uuid4().hex[:8]}", first_name="Idm", last_name="Kid", status="active")
        s.add(st); await s.flush()
        e = Enrollment(id=uuid.uuid4(), student_id=st.id, programme_id="piano",
                       programme_name="Piano", instructor_id=uuid.UUID(ins_id),
                       fee_plan="4_classes", fee_amount=4500, status="active")
        s.add(e); await s.flush()
        w = ClassSchedule(id=uuid.uuid4(), enrollment_id=e.id, instructor_id=uuid.UUID(ins_id),
                          day_of_week="tuesday", start_time=time(16, 0), end_time=time(17, 0),
                          frequency="weekly", is_active=True)
        s.add(w)
        fut = ClassSession(id=uuid.uuid4(), enrollment_id=e.id, student_id=st.id,
                           instructor_id=uuid.UUID(ins_id), scheduled_date=date(2026, 11, 3),
                           scheduled_start=time(16, 0), scheduled_end=time(17, 0), status="scheduled")
        done = ClassSession(id=uuid.uuid4(), enrollment_id=e.id, student_id=st.id,
                            instructor_id=uuid.UUID(ins_id), scheduled_date=date(2026, 10, 6),
                            scheduled_start=time(16, 0), scheduled_end=time(17, 0), status="completed")
        att = Attendance(id=uuid.uuid4(), student_id=st.id, enrollment_id=e.id,
                         instructor_id=uuid.UUID(ins_id), class_date=date(2026, 10, 6), status="present")
        s.add_all([fut, done, att])
        await s.commit()
        return {"student": str(st.id), "enrollment": str(e.id), "weekly": str(w.id),
                "future": str(fut.id), "completed": str(done.id), "attendance": str(att.id)}


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_impact_and_no_dependency_delete(client, admin_user):
    h = auth(admin_user)
    ins_id, user_id = await _mk_instructor("cleanins")
    imp = (await client.get(f"/api/v1/admin/instructors/{ins_id}/delete-impact", headers=h)).json()
    assert imp["students"] == [] and imp["future_sessions"] == []
    assert imp["completed_sessions"] == 0 and imp["weekly_slots"] == 0
    r = await client.delete(f"/api/v1/admin/instructors/{ins_id}", headers=h)
    assert r.status_code == 200 and r.json()["deleted"] is True
    # released login + no longer listed
    lst = (await client.get("/api/v1/admin/instructors", headers=h)).json()
    assert all(x["id"] != ins_id for x in lst)
    login = await client.post("/api/v1/auth/login", json={"email": "cleanins", "password": "4321"})
    assert login.status_code == 401
    # username reusable
    ins2, _ = await _mk_instructor("cleanins")
    assert ins2 != ins_id


@pytest.mark.asyncio
async def test_deactivate_keeps_everything(client, admin_user):
    h = auth(admin_user)
    ins_id, user_id = await _mk_instructor("deactins")
    w = await _mk_world(ins_id)
    r = await client.patch(f"/api/v1/admin/instructors/{ins_id}",
                           json={"is_active": False, "acknowledge_future_classes": True}, headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is False
    async with TestSessionLocal() as s:
        ins = (await s.execute(select(Instructor).where(Instructor.id == uuid.UUID(ins_id)))).scalar_one()
        assert ins.is_active is False
        # sessions/attendance/profile all retained
        n = (await s.execute(select(func.count(ClassSession.id)))).scalar()
        assert n == 2
        a = (await s.execute(select(func.count(Attendance.id)))).scalar()
        assert a == 1
    # reactivate
    r = await client.patch(f"/api/v1/admin/instructors/{ins_id}", json={"is_active": True}, headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is True


@pytest.mark.asyncio
async def test_delete_with_dependencies_unassign_default(client, admin_user):
    h = auth(admin_user)
    ins_id, user_id = await _mk_instructor("depins")
    other_ins, _ = await _mk_instructor("keepins")
    w = await _mk_world(ins_id)
    # unrelated instructor's own session must survive
    async with TestSessionLocal() as s:
        ou = User(id=uuid.uuid4(), username=f"otherstu{uuid.uuid4().hex[:6]}",
                  hashed_password=get_password_hash("1"),
                  role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(ou); await s.flush()
        ost = Student(id=uuid.uuid4(), user_id=ou.id, cma_registration_id=f"CMA-2026-{uuid.uuid4().hex[:5].upper()}",
                      portal_slug=f"p{uuid.uuid4().hex[:8]}", first_name="Other2", last_name="K", status="active")
        s.add(ost); await s.flush()
        oe = Enrollment(id=uuid.uuid4(), student_id=ost.id, programme_id="guitar",
                        programme_name="Guitar", instructor_id=uuid.UUID(other_ins), status="active")
        s.add(oe); await s.flush()
        osess = ClassSession(id=uuid.uuid4(), enrollment_id=oe.id, student_id=ost.id,
                             instructor_id=uuid.UUID(other_ins), scheduled_date=date(2026, 11, 5),
                             scheduled_start=time(10, 0), scheduled_end=time(11, 0), status="scheduled")
        s.add(osess); await s.commit()
        osess_id = str(osess.id)

    imp = (await client.get(f"/api/v1/admin/instructors/{ins_id}/delete-impact", headers=h)).json()
    assert len(imp["students"]) == 1 and imp["weekly_slots"] == 1
    assert len(imp["future_sessions"]) == 1 and imp["completed_sessions"] == 1
    assert imp["attendance_rows"] == 1

    r = await client.delete(f"/api/v1/admin/instructors/{ins_id}", headers=h)   # default unassign
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["future_action"] == "unassign" and body["resolved"]["future_sessions"] == 1

    async with TestSessionLocal() as s:
        # future session kept, instructor cleared
        fut = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(w["future"])))).scalar_one()
        assert fut.status == "scheduled" and fut.instructor_id is None
        # completed history preserved, attribution cleared (never fabricated)
        done = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(w["completed"])))).scalar_one()
        assert done.status == "completed" and done.instructor_id is None
        # attendance row kept
        att = (await s.execute(select(Attendance).where(Attendance.id == uuid.UUID(w["attendance"])))).scalar_one()
        assert att.instructor_id is None
        # weekly row kept for the student (unassigned)
        wk = (await s.execute(select(ClassSchedule).where(ClassSchedule.id == uuid.UUID(w["weekly"])))).scalar_one()
        assert wk.instructor_id is None
        # enrolment unassigned, student profile intact
        e = (await s.execute(select(Enrollment).where(Enrollment.id == uuid.UUID(w["enrollment"])))).scalar_one()
        assert e.instructor_id is None
        st = (await s.execute(select(Student).where(Student.id == uuid.UUID(w["student"])))).scalar_one()
        assert st is not None
        # instructor + user gone
        assert (await s.execute(select(Instructor).where(Instructor.id == uuid.UUID(ins_id)))).scalar_one_or_none() is None
        assert (await s.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one_or_none() is None
        # unrelated instructor's session untouched
        osess = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(osess_id)))).scalar_one()
        assert osess.instructor_id == uuid.UUID(other_ins)

    # login dead; not assignable anymore
    login = await client.post("/api/v1/auth/login", json={"email": "depins", "password": "4321"})
    assert login.status_code == 401
    r = await client.post(f"/api/v1/admin/students/{w['student']}/monthly-schedule",
                          json={"month": "2026-11",
                                "instructor_id": ins_id,
                                "new_days": [{"day": "tuesday", "start_time": "16:00", "end_time": "17:00"}],
                                "effective_date": "2026-11-01", "confirm": True}, headers=h)
    assert r.status_code in (400, 422), r.text   # deleted instructor cannot be assigned


@pytest.mark.asyncio
async def test_delete_cancel_and_reassign_paths(client, admin_user):
    h = auth(admin_user)
    # cancel path
    ins1, _ = await _mk_instructor("canins")
    w1 = await _mk_world(ins1)
    r = await client.delete(f"/api/v1/admin/instructors/{ins1}?future_action=cancel", headers=h)
    assert r.status_code == 200 and r.json()["resolved"]["future_sessions"] == 1
    async with TestSessionLocal() as s:
        fut = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(w1["future"])))).scalar_one()
        assert fut.status == "cancelled"
        done = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(w1["completed"])))).scalar_one()
        assert done.status == "completed"     # history kept even on cancel path

    # reassign path (with validation)
    ins2, _ = await _mk_instructor("reaA")
    ins3, _ = await _mk_instructor("reaB")
    w2 = await _mk_world(ins2)
    r = await client.delete(f"/api/v1/admin/instructors/{ins2}?future_action=reassign", headers=h)
    assert r.status_code == 400              # target required
    r = await client.delete(f"/api/v1/admin/instructors/{ins2}?future_action=reassign&reassign_instructor_id={ins2}", headers=h)
    assert r.status_code == 400              # cannot reassign to self
    r = await client.delete(f"/api/v1/admin/instructors/{ins2}?future_action=reassign&reassign_instructor_id={uuid.uuid4()}", headers=h)
    assert r.status_code == 400              # target must exist
    r = await client.delete(
        f"/api/v1/admin/instructors/{ins2}?future_action=reassign&reassign_instructor_id={ins3}", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reassigned_to"] == str(ins3)
    async with TestSessionLocal() as s:
        fut = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(w2["future"])))).scalar_one()
        assert fut.instructor_id == uuid.UUID(ins3) and fut.status == "scheduled"
        e = (await s.execute(select(Enrollment).where(Enrollment.id == uuid.UUID(w2["enrollment"])))).scalar_one()
        assert e.instructor_id == uuid.UUID(ins3)
        wk = (await s.execute(select(ClassSchedule).where(ClassSchedule.id == uuid.UUID(w2["weekly"])))).scalar_one()
        assert wk.instructor_id == uuid.UUID(ins3)
        done = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(w2["completed"])))).scalar_one()
        assert done.instructor_id is None     # history attribution NOT handed to the new instructor


@pytest.mark.asyncio
async def test_delete_rollback_on_failure(client, admin_user, monkeypatch):
    h = auth(admin_user)
    ins_id, user_id = await _mk_instructor("rollins")
    w = await _mk_world(ins_id)
    import app.api.v1.admin as admin_mod
    def boom(*a, **k):
        raise RuntimeError("audit backend unavailable (injected)")
    monkeypatch.setattr(admin_mod, "record_audit", boom)
    with pytest.raises(RuntimeError):
        await client.delete(f"/api/v1/admin/instructors/{ins_id}?future_action=cancel", headers=h)
    async with TestSessionLocal() as s:
        # everything intact after rollback
        assert (await s.execute(select(Instructor).where(Instructor.id == uuid.UUID(ins_id)))).scalar_one() is not None
        assert (await s.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one() is not None
        fut = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(w["future"])))).scalar_one()
        assert fut.status == "scheduled" and fut.instructor_id == uuid.UUID(ins_id)
        e = (await s.execute(select(Enrollment).where(Enrollment.id == uuid.UUID(w["enrollment"])))).scalar_one()
        assert e.instructor_id == uuid.UUID(ins_id)
