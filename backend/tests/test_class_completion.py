"""
Class completion, admin corrections, and instructor/completion reports.
"""
import uuid
from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_class_completion.db"
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
async def setup_world():
    """One admin, one instructor (with student), one foreign instructor, one student."""
    async with TestSessionLocal() as db:
        admin_u = User(username="ccadmin", email="ccadmin@t.local",
                       hashed_password=get_password_hash("AdminPass@123"),
                       role=UserRole.ADMIN, is_active=True)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="CC", last_name="Admin",
                     admin_level="super_admin", is_active=True))
        await db.flush()

        inst_u = User(username="ccinst", email="ccinst@t.local",
                      hashed_password=get_password_hash("InstPass@123"),
                      role=UserRole.INSTRUCTOR, is_active=True)
        db.add(inst_u)
        await db.flush()
        inst = Instructor(user_id=inst_u.id, first_name="CC", last_name="Faculty",
                          specializations="Piano", is_active=True)
        db.add(inst)

        other_u = User(username="ccother", email="ccother@t.local",
                       hashed_password=get_password_hash("InstPass@123"),
                       role=UserRole.INSTRUCTOR, is_active=True)
        db.add(other_u)
        await db.flush()
        other = Instructor(user_id=other_u.id, first_name="Oth", last_name="Er",
                           specializations="Guitar", is_active=True)
        db.add(other)

        stu_u = User(username="CMA-7001", email=None,
                     hashed_password=get_password_hash("7001"),
                     role=UserRole.STUDENT, is_active=True)
        db.add(stu_u)
        await db.flush()
        stu = Student(user_id=stu_u.id, cma_registration_id="CMA-2026-7001",
                      portal_slug="cstu", first_name="Comp", last_name="Tester",
                      status="active", profile_complete=False)
        db.add(stu)
        await db.flush()

        enr = Enrollment(student_id=stu.id, programme_id="piano", programme_name="Piano",
                         instructor_id=inst.id, fee_plan="4_classes", fee_amount=4500,
                         status="active")
        db.add(enr)
        await db.commit()
        return {
            "admin": admin_u, "instructor": inst_u, "instructor_id": inst.id,
            "other": other_u, "other_id": other.id,
            "student": stu_u, "student_id": stu.id, "enrollment_id": enr.id,
        }


async def _mk_session(db, enrollment_id, student_id, instructor_id,
                      days_offset, start=(17, 0), end=(18, 0), status="scheduled", **kw):
    sess = ClassSession(
        enrollment_id=enrollment_id, student_id=student_id, instructor_id=instructor_id,
        scheduled_date=date.today() + timedelta(days=days_offset),
        scheduled_start=time(*start), scheduled_end=time(*end),
        timezone="Asia/Kolkata", status=status, **kw)
    db.add(sess)
    await db.flush()
    return sess


# ---------------------------------------------------------------------------
# 1. Instructor marks a class completed with notes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_instructor_completes_class_with_notes(client, setup_world):
    w = setup_world
    async with TestSessionLocal() as db:
        # past class still 'scheduled' → awaiting update, NOT auto-completed
        past = await _mk_session(db, w["enrollment_id"], w["student_id"], w["instructor_id"], -2)
        await db.commit()
        past_id = str(past.id)

    # nothing auto-completed
    listed = await client.get("/api/v1/sessions?limit=50", headers=auth(w["instructor"]))
    row = [x for x in listed.json() if x["id"] == past_id][0]
    assert row["status"] == "scheduled"
    assert row["student_name"] == "Comp Tester"      # enrichment for instructor
    assert row["programme"] == "Piano"

    done = await client.post(f"/api/v1/sessions/{past_id}/complete", json={
        "topics_covered": "C major scale, Minuet",
        "faculty_remarks": "Good progress on fingering",
        "practice_recommendations": "Minuet hands separately, 15 min daily",
    }, headers=auth(w["instructor"]))
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "completed"
    assert body["practice_recommendations"] == "Minuet hands separately, 15 min daily"
    assert body["actual_date"] is not None

    async with TestSessionLocal() as db:
        sess = (await db.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(past_id)))).scalar_one()
        assert sess.status == "completed"
        assert sess.topics_covered == "C major scale, Minuet"
        assert sess.practice_recommendations is not None
        assert sess.updated_by is not None
        hist = (await db.execute(select(SessionStatusHistory).where(
            SessionStatusHistory.session_id == sess.id))).scalars().all()
        assert any(h.to_status == "completed" for h in hist)
        audits = (await db.execute(select(AuditEvent).where(
            AuditEvent.action == "session.completed"))).scalars().all()
        assert len(audits) == 1


# ---------------------------------------------------------------------------
# 2. Duplicate completion is rejected (idempotent protection)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_duplicate_completion_rejected(client, setup_world):
    w = setup_world
    async with TestSessionLocal() as db:
        sess = await _mk_session(db, w["enrollment_id"], w["student_id"], w["instructor_id"], 1)
        await db.commit()
        sid = str(sess.id)
    first = await client.post(f"/api/v1/sessions/{sid}/complete", json={"topics_covered": "t"},
                              headers=auth(w["instructor"]))
    assert first.status_code == 200
    second = await client.post(f"/api/v1/sessions/{sid}/complete", json={"topics_covered": "t2"},
                               headers=auth(w["instructor"]))
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# 3. Authorization boundaries
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_completion_authorization(client, setup_world):
    w = setup_world
    async with TestSessionLocal() as db:
        sess = await _mk_session(db, w["enrollment_id"], w["student_id"], w["instructor_id"], 1)
        await db.commit()
        sid = str(sess.id)
    # another instructor cannot complete
    r = await client.post(f"/api/v1/sessions/{sid}/complete", json={}, headers=auth(w["other"]))
    assert r.status_code == 403
    # student cannot complete
    tok = _make_token(w["student"])
    r = await client.post(f"/api/v1/sessions/{sid}/complete", json={},
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code in (403, 422, 400)
    # student cannot correct
    r = await client.post(f"/api/v1/sessions/{sid}/correction",
                          json={"topics_covered": "x", "reason": "try"},
                          headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
    # instructor cannot correct (admin only)
    r = await client.post(f"/api/v1/sessions/{sid}/correction",
                          json={"topics_covered": "x", "reason": "try"},
                          headers=auth(w["instructor"]))
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# 4. Admin correction with audit trail, idempotent on repeat
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_correction_audit(client, setup_world):
    w = setup_world
    async with TestSessionLocal() as db:
        sess = await _mk_session(db, w["enrollment_id"], w["student_id"], w["instructor_id"], -1)
        await db.commit()
        sid = str(sess.id)
    await client.post(f"/api/v1/sessions/{sid}/complete",
                      json={"topics_covered": "wrong date keyed"},
                      headers=auth(w["instructor"]))

    corr = await client.post(f"/api/v1/sessions/{sid}/correction", json={
        "actual_date": (date.today() - timedelta(days=2)).isoformat(),
        "topics_covered": "corrected topics",
        "practice_recommendations": "corrected practice",
        "reason": "mis-keyed completion date",
    }, headers=auth(w["admin"]))
    assert corr.status_code == 200, corr.text
    assert corr.json()["changed"] is True

    async with TestSessionLocal() as db:
        sess = (await db.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(sid)))).scalar_one()
        assert sess.topics_covered == "corrected topics"
        assert sess.actual_date == date.today() - timedelta(days=2)
        corrections = (await db.execute(select(AuditEvent).where(
            AuditEvent.action == "session.corrected"))).scalars().all()
        assert len(corrections) == 1
        assert "mis-keyed" in corrections[0].summary
        hist = (await db.execute(select(SessionStatusHistory).where(
            SessionStatusHistory.session_id == sess.id))).scalars().all()
        assert any("corrected" in (h.reason or "") for h in hist)

    # repeat with identical values → no-op (idempotent)
    again = await client.post(f"/api/v1/sessions/{sid}/correction", json={
        "actual_date": (date.today() - timedelta(days=2)).isoformat(),
        "topics_covered": "corrected topics",
        "practice_recommendations": "corrected practice",
        "reason": "duplicate submit",
    }, headers=auth(w["admin"]))
    assert again.status_code == 200 and again.json()["changed"] is False


# ---------------------------------------------------------------------------
# 5. Report totals, completion rate, per-instructor breakdown, filters
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_class_completion_report(client, setup_world):
    w = setup_world
    async with TestSessionLocal() as db:
        # completed (past)
        c1 = await _mk_session(db, w["enrollment_id"], w["student_id"], w["instructor_id"], -3,
                               status="scheduled")
        # awaiting update (past, still scheduled)
        await _mk_session(db, w["enrollment_id"], w["student_id"], w["instructor_id"], -2)
        # future scheduled
        await _mk_session(db, w["enrollment_id"], w["student_id"], w["instructor_id"], 3)
        # cancelled
        await _mk_session(db, w["enrollment_id"], w["student_id"], w["instructor_id"], 4,
                          status="cancelled")
        await db.commit()
        c1_id = str(c1.id)
    await client.post(f"/api/v1/sessions/{c1_id}/complete",
                      json={"topics_covered": "done", "faculty_remarks": "ok"},
                      headers=auth(w["instructor"]))

    rep = await client.get("/api/v1/admin/reports/class-completion", headers=auth(w["admin"]))
    assert rep.status_code == 200
    body = rep.json()
    t = body["totals"]
    assert t["completed"] == 1
    assert t["awaiting_update"] == 1
    assert t["scheduled_upcoming"] == 1
    assert t["cancelled"] == 1
    assert t["total"] == 4
    assert t["completion_rate_pct"] == 50.0      # 1 completed / 2 past deliverables
    assert t["last_completion_update"] is not None
    # per-instructor breakdown
    ig = body["by_instructor"][0]
    assert ig["instructor_name"] == "CC Faculty"
    assert ig["completed"] == 1 and ig["awaiting_update"] == 1
    # filters: instructor + status
    f1 = await client.get(f"/api/v1/admin/reports/class-completion?instructor_id={w['instructor_id']}&status=completed",
                          headers=auth(w["admin"]))
    assert f1.json()["totals"]["total"] == 1 and f1.json()["totals"]["completed"] == 1
    # filter by course
    f2 = await client.get("/api/v1/admin/reports/class-completion?programme=Piano", headers=auth(w["admin"]))
    assert f2.json()["totals"]["total"] == 4
    # instructor cannot access the report
    deny = await client.get("/api/v1/admin/reports/class-completion", headers=auth(w["instructor"]))
    assert deny.status_code == 403


# ---------------------------------------------------------------------------
# 6. Confirmed reschedule sets the original to 'rescheduled'
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reschedule_sets_rescheduled_state(client, setup_world):
    w = setup_world
    async with TestSessionLocal() as db:
        sess = await _mk_session(db, w["enrollment_id"], w["student_id"], w["instructor_id"], 5)
        await db.commit()
        sid = str(sess.id)
    tok = _make_token(w["student"])
    await client.post(f"/api/v1/sessions/{sid}/flag-reschedule",
                      json={"reason": "travel"}, headers={"Authorization": f"Bearer {tok}"})
    await client.post(f"/api/v1/sessions/{sid}/reschedule",
                      json={"new_date": (date.today() + timedelta(days=8)).isoformat(),
                            "new_start": "18:00", "new_end": "19:00", "reason": "approved by academy"},
                      headers=auth(w["admin"]))
    async with TestSessionLocal() as db:
        original = (await db.execute(select(ClassSession).where(ClassSession.id == uuid.UUID(sid)))).scalar_one()
        assert original.status == "rescheduled"
    # the flagged state before confirmation is distinct
    # (covered by test_workflow_fixes); report counts both states separately
    rep = await client.get("/api/v1/admin/reports/class-completion", headers=auth(w["admin"]))
    t = rep.json()["totals"]
    assert t["rescheduled"] == 1
