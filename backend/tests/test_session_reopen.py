"""
Undo completion ("mark as uncompleted"): restores scheduled state, clears
completion details, keeps history/audit, recomputes payouts, enforces role
ownership, and allows editing after the undo.
"""
import uuid
from datetime import date, datetime, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_session_reopen.db"
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
from app.models.session import ClassSession, SessionStatus, SessionStatusHistory
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
        u = User(id=uuid.uuid4(), username="ropenadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Ro", last_name="Pen",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _world():
    """admin + owning instructor + other instructor + student/enrolment/session."""
    async with TestSessionLocal() as s:
        iu = User(id=uuid.uuid4(), username="ownins", hashed_password=get_password_hash("1234"),
                  role=UserRole.INSTRUCTOR, is_active=True, must_change_pin=False)
        s.add(iu); await s.flush()
        own = Instructor(id=uuid.uuid4(), user_id=iu.id, first_name="Own", last_name="Teach", is_active=True)
        s.add(own)
        ou = User(id=uuid.uuid4(), username="otherins2", hashed_password=get_password_hash("1234"),
                  role=UserRole.INSTRUCTOR, is_active=True, must_change_pin=False)
        s.add(ou); await s.flush()
        other = Instructor(id=uuid.uuid4(), user_id=ou.id, first_name="Other", last_name="Teach", is_active=True)
        s.add(other)
        su = User(id=uuid.uuid4(), username="rostu", hashed_password=get_password_hash("1234"),
                  role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(su); await s.flush()
        st = Student(id=uuid.uuid4(), user_id=su.id, cma_registration_id=f"CMA-2026-{uuid.uuid4().hex[:5].upper()}",
                     portal_slug=f"p{uuid.uuid4().hex[:8]}", first_name="Ro", last_name="Stu", status="active")
        s.add(st); await s.flush()
        e = Enrollment(id=uuid.uuid4(), student_id=st.id, programme_id="piano", programme_name="Piano",
                       instructor_id=own.id, fee_plan="4_classes", fee_amount=4500, status="active")
        s.add(e); await s.flush()
        sess = ClassSession(id=uuid.uuid4(), enrollment_id=e.id, student_id=st.id,
                            instructor_id=own.id, scheduled_date=date(2026, 12, 7),
                            scheduled_start=time(10, 0), scheduled_end=time(11, 0),
                            status=SessionStatus.SCHEDULED)
        s.add(sess); await s.commit()
        return {"own_instructor": str(own.id), "own_user": str(iu.id),
                "other_user": str(ou.id), "student_user": str(su.id),
                "session": str(sess.id), "enrollment": str(e.id)}


async def _complete(session_id, h, actual_date="2026-12-07"):
    return await h["c"].post(f"/api/v1/sessions/{session_id}/complete",
                             json={"actual_date": actual_date, "topics_covered": "scales"},
                             headers=h["h"])


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_complete_then_undo_restores_scheduled(client, admin_user):
    w = await _world()
    h = {"c": client, "h": auth(admin_user)}
    r = await _complete(w["session"], h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"
    async with TestSessionLocal() as s:
        sess = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(w["session"])))).scalar_one()
        assert sess.billing_month == "2026-12" and sess.actual_date is not None
        hist_before = (await s.execute(select(func.count(SessionStatusHistory.id)))).scalar()

    r = await client.post(f"/api/v1/sessions/{w['session']}/reopen",
                          json={"reason": "Wrong student recorded"}, headers=auth(admin_user))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "scheduled"
    async with TestSessionLocal() as s:
        sess = (await s.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(w["session"])))).scalar_one()
        assert sess.status == SessionStatus.SCHEDULED
        assert sess.actual_date is None and sess.actual_start is None
        assert sess.actual_end is None and sess.actual_duration_minutes is None
        assert sess.billing_month is None            # removed from delivered-month attribution
        hist = (await s.execute(select(SessionStatusHistory).where(
            SessionStatusHistory.session_id == sess.id).order_by(
            SessionStatusHistory.changed_at))).scalars().all()
        assert len(hist) >= hist_before              # history APPENDED, never erased
        assert hist[-1].to_status == SessionStatus.SCHEDULED
        assert "wrong student" in (hist[-1].reason or "").lower()
        ev = (await s.execute(select(AuditEvent).where(
            AuditEvent.action == "session.reopened"))).scalars().all()
        assert ev and str(sess.id) in (ev[-1].entity_id or "")

    # re-complete works after the undo
    r = await _complete(w["session"], h)
    assert r.status_code == 200 and r.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_reopen_guards(client, admin_user):
    w = await _world()
    ah = auth(admin_user)
    # cannot undo a session that is not completed
    r = await client.post(f"/api/v1/sessions/{w['session']}/reopen", json={}, headers=ah)
    assert r.status_code == 409
    # complete → undo → undo again refused
    await client.post(f"/api/v1/sessions/{w['session']}/complete",
                      json={"actual_date": "2026-12-07"}, headers=ah)
    r = await client.post(f"/api/v1/sessions/{w['session']}/reopen", json={}, headers=ah)
    assert r.status_code == 200
    r = await client.post(f"/api/v1/sessions/{w['session']}/reopen", json={}, headers=ah)
    assert r.status_code == 409
    # students cannot undo
    async with TestSessionLocal() as s:
        su_id = uuid.UUID(w["student_user"])
    sh = {"Authorization": f"Bearer {create_access_token(data={'sub': str(su_id), 'role': 'student'}, expires_delta=timedelta(minutes=5))}"}
    await client.post(f"/api/v1/sessions/{w['session']}/complete",
                      json={"actual_date": "2026-12-07"}, headers=ah)
    r = await client.post(f"/api/v1/sessions/{w['session']}/reopen", json={}, headers=sh)
    assert r.status_code == 403
    # a DIFFERENT instructor cannot undo someone else's session
    oh = {"Authorization": f"Bearer {create_access_token(data={'sub': w['other_user'], 'role': 'instructor'}, expires_delta=timedelta(minutes=5))}"}
    r = await client.post(f"/api/v1/sessions/{w['session']}/reopen", json={}, headers=oh)
    assert r.status_code in (403, 404)


@pytest.mark.asyncio
async def test_owner_instructor_can_undo_and_edit_afterwards(client, admin_user):
    w = await _world()
    ih = {"Authorization": f"Bearer {create_access_token(data={'sub': w['own_user'], 'role': 'instructor'}, expires_delta=timedelta(minutes=5))}"}
    # owner marks completed
    r = await client.post(f"/api/v1/sessions/{w['session']}/complete",
                          json={"actual_date": "2026-12-07"}, headers=ih)
    assert r.status_code == 200, r.text
    # owner undoes it (the mistaken-mark scenario)
    r = await client.post(f"/api/v1/sessions/{w['session']}/reopen",
                          json={"reason": "Marked against the wrong student"}, headers=ih)
    assert r.status_code == 200, r.text
    # after undo the session is editable again (PATCH against the schedule)
    r = await client.patch(f"/api/v1/sessions/{w['session']}",
                           json={"scheduled_start": "11:00", "scheduled_end": "12:00"}, headers=ih)
    assert r.status_code == 200, r.text
    assert r.json()["scheduled_start"].startswith("11:00")


@pytest.mark.asyncio
async def test_undo_recomputes_instructor_payout(client, admin_user):
    w = await _world()
    ah = auth(admin_user)
    # configure a rate for the owning instructor (employment + individual rate)
    await client.patch(f"/api/v1/admin/instructors/{w['own_instructor']}",
                       json={"employment_type": "regular"}, headers=ah)
    await client.post(f"/api/v1/admin/instructors/{w['own_instructor']}/rate",
                      json={"per_class_rate_paise": 50000, "effective_from": "2026-01-01"}, headers=ah)
    await client.post(f"/api/v1/sessions/{w['session']}/complete",
                      json={"actual_date": "2026-12-07"}, headers=ah)
    calc = (await client.get(f"/api/v1/admin/instructors/{w['own_instructor']}/payouts?month=2026-12",
                             headers=ah)).json()
    assert calc["payable_paise"] == 50000 and calc["completed_count"] == 1
    # undo → payable drops automatically (no manual recalculation)
    r = await client.post(f"/api/v1/sessions/{w['session']}/reopen", json={}, headers=ah)
    assert r.status_code == 200
    calc = (await client.get(f"/api/v1/admin/instructors/{w['own_instructor']}/payouts?month=2026-12",
                             headers=ah)).json()
    assert calc["completed_count"] == 0 and calc["payable_paise"] == 0
