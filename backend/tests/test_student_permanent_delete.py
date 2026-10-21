"""
Permanent student deletion: impact report, dependency cleanup, financial
retention, identifier reuse, rollback on failure, unrelated-data safety.
"""
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_student_delete.db"
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
from app.models.class_schedule import ClassSchedule
from app.models.session import ClassSession
from app.models.learning import Assignment
from app.models.attendance import Attendance
from app.models.fee_record import FeeRecord
from app.models.billing import Invoice
from app.models.notification import Notification


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
    transport = ASGITransport(app=app, raise_app_exceptions=True)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def admin_user():
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username="deladmin", email=None,
                 hashed_password=get_password_hash("0000"), role=UserRole.ADMIN,
                 is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Del", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _mk_student(username: str, reg: str, name: str = "Del Testee") -> tuple[uuid.UUID, uuid.UUID]:
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=username, email=None,
                 hashed_password=get_password_hash("1234"), role=UserRole.STUDENT,
                 is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        st = Student(id=uuid.uuid4(), user_id=u.id, cma_registration_id=reg,
                     portal_slug=username.lower(), first_name=name, last_name="T",
                     status="active")
        s.add(st)
        await s.commit()
        return st.id, u.id


async def _mk_deps(student_id: uuid.UUID) -> dict:
    """enrollment + schedule + session + assignment + attendance + financials."""
    from datetime import date as _date, time as _time
    from app.models.instructor import Instructor
    async with TestSessionLocal() as s:
        # attendance requires an instructor — build one (user + profile)
        iu = User(id=uuid.uuid4(), username=f"delins{uuid.uuid4().hex[:6]}",
                  hashed_password=get_password_hash("1234"), role=UserRole.INSTRUCTOR,
                  is_active=True, must_change_pin=False)
        s.add(iu)
        await s.flush()
        ins = Instructor(id=uuid.uuid4(), user_id=iu.id, first_name="Del", last_name="Ins",
                         is_active=True)
        s.add(ins)
        e = Enrollment(id=uuid.uuid4(), student_id=student_id, programme_id="piano",
                       programme_name="Piano", instructor_id=ins.id, fee_plan="4_classes",
                       fee_amount=4500, status="active")
        s.add(e)
        await s.flush()
        sch = ClassSchedule(id=uuid.uuid4(), enrollment_id=e.id, instructor_id=ins.id,
                            day_of_week="monday", start_time=_time(10, 0),
                            end_time=_time(11, 0), frequency="weekly", is_active=True)
        sess = ClassSession(id=uuid.uuid4(), enrollment_id=e.id, student_id=student_id,
                            instructor_id=ins.id, scheduled_date=_date(2026, 11, 2),
                            scheduled_start=_time(10, 0), scheduled_end=_time(11, 0),
                            duration_minutes=60, status="scheduled")
        asg = Assignment(id=uuid.uuid4(), student_id=student_id, enrollment_id=e.id,
                         title="Scale drill", assigned_date=_date(2026, 10, 20),
                         status="assigned")
        att = Attendance(id=uuid.uuid4(), student_id=student_id, enrollment_id=e.id,
                         instructor_id=ins.id, class_date=_date(2026, 10, 19),
                         status="present")
        fr = FeeRecord(id=uuid.uuid4(), enrollment_id=e.id, student_id=student_id,
                       fee_plan="4_classes", period="2026-10",
                       amount_expected=4500, amount_paid=0,
                       payment_status="pending")
        inv = Invoice(id=uuid.uuid4(), invoice_number=f"DEL/INV/{uuid.uuid4().hex[:8]}",
                      enrollment_id=e.id, student_id=student_id,
                      billing_month="2026-10", amount_paise=450000, status="pending")
        owner_uid = (await s.execute(
            select(Student.user_id).where(Student.id == student_id))).scalar()
        notif = Notification(id=uuid.uuid4(), user_id=owner_uid, type="class.reminder",
                             title="Welcome", body="hello",
                             dedupe_key=f"del-{uuid.uuid4().hex[:12]}")
        s.add_all([sch, sess, asg, att, fr, inv, notif])
        await s.commit()
        return {"enrollment": e.id, "session": sess.id, "assignment": asg.id,
                "schedule": sch.id, "attendance": att.id, "fee": fr.id, "invoice": inv.id}


async def _exists(model, rid) -> bool:
    async with TestSessionLocal() as s:
        return (await s.execute(select(func.count()).select_from(model).where(model.id == rid))).scalar() > 0


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_delete_student_without_dependencies(client, admin_user):
    sid, uid = await _mk_student("clean.user", "CMA-2026-9001", "Clean")
    h = auth(admin_user)

    imp = await client.get(f"/api/v1/admin/students/{sid}/delete-impact", headers=h)
    assert imp.status_code == 200
    body = imp.json()
    assert body["archive_recommended"] is False
    assert all(v == 0 for v in body["remove"].values())
    assert any("irreversible" in w.lower() for w in body["warnings"])

    r = await client.delete(f"/api/v1/admin/students/{sid}", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["deleted"] is True
    assert d["released"]["username"] == "clean.user"
    assert d["released"]["cma_registration_id"] == "CMA-2026-9001"
    # NOT transformed into an archive
    assert await _exists(Student, sid) is False
    assert await _exists(User, uid) is False

    # deleted account cannot log in (its user row is gone)
    login = await client.post("/api/v1/auth/login",
                              json={"email": "clean.user", "password": "1234"})
    assert login.status_code == 401

    # identifiers reusable immediately
    sid2, uid2 = await _mk_student("clean.user", "CMA-2026-9001")
    assert sid2 != sid


@pytest.mark.asyncio
async def test_delete_student_with_dependencies_and_retention(client, admin_user):
    h = auth(admin_user)
    sid, uid = await _mk_student("dep.user", "CMA-2026-9002", "Dep")
    deps = await _mk_deps(sid)
    # unrelated student that must survive untouched
    sid_other, uid_other = await _mk_student("keep.user", "CMA-2026-9003", "Keep")
    deps_other = await _mk_deps(sid_other)

    imp = await client.get(f"/api/v1/admin/students/{sid}/delete-impact", headers=h)
    assert imp.status_code == 200
    body = imp.json()
    assert body["archive_recommended"] is True
    assert body["remove"]["enrollments"] == 1
    assert body["remove"]["class_sessions"] == 1
    assert body["remove"]["class_schedules"] == 1
    assert body["remove"]["assignments"] == 1
    assert body["remove"]["attendance"] == 1
    assert body["retain_unlinked"]["invoices"] == 1
    assert body["retain_unlinked"]["fee_records"] == 1
    assert any("RECOMMENDED" in w for w in body["warnings"])

    r = await client.delete(f"/api/v1/admin/students/{sid}", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["removed"]["enrollments"] == 1
    assert d["removed"]["class_sessions"] == 1
    assert d["retained_unlinked"]["invoices"] == 1
    assert d["retained_unlinked"]["fee_records"] == 1
    assert d["released"]["username"] == "dep.user"

    # academic rows for THIS student are gone
    for model, rid in ((Enrollment, deps["enrollment"]), (ClassSession, deps["session"]),
                       (ClassSchedule, deps["schedule"]), (Assignment, deps["assignment"]),
                       (Attendance, deps["attendance"])):
        assert await _exists(model, rid) is False, model.__name__
    assert await _exists(Student, sid) is False
    assert await _exists(User, uid) is False

    # financial records RETAINED with the student link released
    async with TestSessionLocal() as s:
        fr = (await s.execute(select(FeeRecord).where(FeeRecord.id == deps["fee"]))).scalar_one()
        inv = (await s.execute(select(Invoice).where(Invoice.id == deps["invoice"]))).scalar_one()
        assert fr.student_id is None and fr.enrollment_id is None
        assert inv.student_id is None and inv.enrollment_id is None
        assert inv.invoice_number.startswith("DEL/INV/")
        assert inv.amount_paise == 450000  # amount untouched

    # unrelated student + their rows intact
    assert await _exists(Student, sid_other) is True
    assert await _exists(User, uid_other) is True
    assert await _exists(Enrollment, deps_other["enrollment"]) is True
    assert await _exists(ClassSession, deps_other["session"]) is True
    async with TestSessionLocal() as s:
        fr2 = (await s.execute(select(FeeRecord).where(FeeRecord.id == deps_other["fee"]))).scalar_one()
        assert fr2.student_id == sid_other  # not nulled

    # reused identifiers work for a fresh profile
    sid3, _ = await _mk_student("dep.user", "CMA-2026-9002")
    assert sid3 != sid


@pytest.mark.asyncio
async def test_delete_rolls_back_when_a_step_fails(client, admin_user, monkeypatch):
    h = auth(admin_user)
    sid, uid = await _mk_student("rollback.user", "CMA-2026-9004")
    deps = await _mk_deps(sid)

    import app.api.v1.admin as admin_mod

    def boom(*a, **k):
        raise RuntimeError("audit backend unavailable (injected)")

    monkeypatch.setattr(admin_mod, "record_audit", boom)

    with pytest.raises(RuntimeError):
        await client.delete(f"/api/v1/admin/students/{sid}", headers=h)

    # full rollback: student, user and every dependency row survive
    assert await _exists(Student, sid) is True
    assert await _exists(User, uid) is True
    assert await _exists(Enrollment, deps["enrollment"]) is True
    assert await _exists(ClassSession, deps["session"]) is True
    assert await _exists(FeeRecord, deps["fee"]) is True
    async with TestSessionLocal() as s:
        fr = (await s.execute(select(FeeRecord).where(FeeRecord.id == deps["fee"]))).scalar_one()
        assert fr.student_id == sid  # retention unlink also rolled back


@pytest.mark.asyncio
async def test_delete_requires_admin_role(client, admin_user):
    sid, _ = await _mk_student("nope.user", "CMA-2026-9005")
    from app.models.instructor import Instructor
    async with TestSessionLocal() as s:
        iu = User(id=uuid.uuid4(), username="plainuser", hashed_password=get_password_hash("1234"),
                  role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(iu)
        await s.commit()
        tok = create_access_token(data={"sub": str(iu.id), "role": "student"},
                                  expires_delta=timedelta(minutes=5))
    r = await client.delete(f"/api/v1/admin/students/{sid}",
                            headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    assert await _exists(Student, sid) is True
