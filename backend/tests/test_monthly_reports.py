"""
Automatic monthly instructor reports.

- Draft generation uses actual class-completion records.
- Missing lesson notes are shown as missing, never fabricated.
- Instructor-written fields survive regeneration.
- Draft -> submitted -> published (admin approval) states are enforced.
- No duplicate reports per enrolment/month; versions via revision.
"""
import uuid
from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_monthly_reports.db"
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
from app.models.reports import MonthlyReport

# a fixed "current month" for record fixtures
Y, M = 2026, 7


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
        admin_u = User(username="mradmin", email="mradmin@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="MR", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        inst_u = User(username="mrinst", email="mrinst@t.local",
                      hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(inst_u)
        await db.flush()
        inst = Instructor(user_id=inst_u.id, first_name="MR", last_name="Faculty",
                          specializations="piano", is_active=True)
        db.add(inst)

        other_u = User(username="mrother", email="mrother@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(other_u)
        await db.flush()
        other = Instructor(user_id=other_u.id, first_name="Un", last_name="Assigned",
                           specializations="guitar", is_active=True)
        db.add(other)

        stu_u = User(username="CMA-9201", hashed_password=get_password_hash("9201"),
                     role=UserRole.STUDENT)
        db.add(stu_u)
        await db.flush()
        stu = Student(user_id=stu_u.id, cma_registration_id="CMA-2026-9201",
                      first_name="Mel", last_name="Ody", status="active")
        db.add(stu)
        await db.flush()
        enr = Enrollment(student_id=stu.id, programme_id="piano", programme_name="Piano",
                         instructor_id=inst.id, fee_plan="4_classes", fee_amount=4500,
                         status="active")
        db.add(enr)
        await db.commit()
        return {"admin": admin_u, "instructor": inst_u, "inst_id": inst.id,
                "other": other_u, "student": stu_u, "student_id": stu.id,
                "enrollment_id": enr.id}


async def _add_session(db, w, day, status="completed", topics=None, practice=None):
    sess = ClassSession(
        enrollment_id=w["enrollment_id"], student_id=w["student_id"],
        instructor_id=w["inst_id"],
        scheduled_date=date(Y, M, day),
        scheduled_start=time(17, 0), scheduled_end=time(18, 0),
        timezone="Asia/Kolkata", status=status,
        topics_covered=topics, practice_recommendations=practice)
    db.add(sess)
    await db.flush()
    return sess


@pytest_asyncio.fixture
async def with_records(world):
    async with TestSessionLocal() as db:
        await _add_session(db, world, 3, topics="C major scale", practice="15 min daily")
        await _add_session(db, world, 10)                      # completed, no notes
        await _add_session(db, world, 17, status="scheduled")  # future/undelivered in month
        await db.commit()
    return world


# ---------------------------------------------------------------------------
# 1. Draft generation uses actual class notes
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_draft_uses_real_class_records(client, with_records):
    w = with_records
    r = await client.post("/api/v1/learning/reports/generate-draft",
                          json={"enrollment_id": str(w["enrollment_id"]),
                                "report_month": f"{Y}-{M:02d}"},
                          headers=auth(w["instructor"]))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "draft"
    assert "C major scale" in body["topics_covered"]
    assert "15 min daily" in body["practice_recommendations"]
    assert "2 of 3" in body["progress_summary"] or "2 of 2" in body["progress_summary"]
    stats = body["generated_from_sessions"]
    assert stats["completed"] == 2
    assert stats["missing_lesson_notes"] == 1


# ---------------------------------------------------------------------------
# 2. Missing notes are never fabricated
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_notes_shown_not_fabricated(client, with_records):
    w = with_records
    r = await client.post("/api/v1/learning/reports/generate-draft",
                          json={"enrollment_id": str(w["enrollment_id"]),
                                "report_month": f"{Y}-{M:02d}"},
                          headers=auth(w["instructor"]))
    body = r.json()
    # the note-less completed class (10 Jul) must be flagged, not summarised
    assert "[no lesson note recorded for this class]" in body["topics_covered"]
    assert "10 Jul" in body["topics_covered"]
    # practice list has only the one real entry — nothing invented
    assert body["practice_recommendations"].count("—") == 1


@pytest.mark.asyncio
async def test_empty_month_produces_explicit_placeholder(client, world):
    w = world
    r = await client.post("/api/v1/learning/reports/generate-draft",
                          json={"enrollment_id": str(w["enrollment_id"]),
                                "report_month": "2026-08"},
                          headers=auth(w["instructor"]))
    assert r.status_code == 201
    body = r.json()
    assert body["topics_covered"] == "[no completed classes recorded for this month]"
    assert body["practice_recommendations"] == "[no practice recommendations recorded]"
    assert "[no completed class records" in body["progress_summary"]


# ---------------------------------------------------------------------------
# 3. Instructor edits persist; regeneration never clobbers without confirmation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_instructor_fields_survive_regeneration(client, with_records):
    w = with_records
    created = await client.post("/api/v1/learning/reports/generate-draft",
                                json={"enrollment_id": str(w["enrollment_id"]),
                                      "report_month": f"{Y}-{M:02d}"},
                                headers=auth(w["instructor"]))
    rid = created.json()["id"]

    edit = await client.patch(f"/api/v1/learning/reports/{rid}",
                              json={"student_id": str(w["student_id"]),
                                    "enrollment_id": str(w["enrollment_id"]),
                                    "report_month": f"{Y}-{M:02d}",
                                    "strengths": "Confident with scales",
                                    "next_month_focus": "Begin first piece"},
                              headers=auth(w["instructor"]))
    assert edit.status_code == 200

    # silent regeneration is refused
    again = await client.post("/api/v1/learning/reports/generate-draft",
                              json={"enrollment_id": str(w["enrollment_id"]),
                                    "report_month": f"{Y}-{M:02d}"},
                              headers=auth(w["instructor"]))
    assert again.status_code == 409

    # explicit confirmation refreshes derived fields but keeps instructor notes
    regen = await client.post("/api/v1/learning/reports/generate-draft",
                              json={"enrollment_id": str(w["enrollment_id"]),
                                    "report_month": f"{Y}-{M:02d}",
                                    "confirm_overwrite": True},
                              headers=auth(w["instructor"]))
    assert regen.status_code == 201
    body = regen.json()
    assert body["id"] == rid
    assert body["strengths"] == "Confident with scales"
    assert body["next_month_focus"] == "Begin first piece"
    assert "C major scale" in body["topics_covered"]

    # ... and the edits are still there on reload
    view = await client.get(f"/api/v1/learning/reports?student_id={w['student_id']}",
                            headers=auth(w["instructor"]))
    row = [x for x in view.json() if x["id"] == rid][0]
    assert row["strengths"] == "Confident with scales"


# ---------------------------------------------------------------------------
# 4. Draft -> submitted -> published states
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_submit_and_approve_workflow(client, with_records):
    w = with_records
    created = await client.post("/api/v1/learning/reports/generate-draft",
                                json={"enrollment_id": str(w["enrollment_id"]),
                                      "report_month": f"{Y}-{M:02d}"},
                                headers=auth(w["instructor"]))
    rid = created.json()["id"]

    # only the assigned instructor/admin can submit
    deny = await client.post(f"/api/v1/learning/reports/{rid}/submit",
                             headers=auth(w["other"]))
    assert deny.status_code == 403

    sub = await client.post(f"/api/v1/learning/reports/{rid}/submit",
                            headers=auth(w["instructor"]))
    assert sub.status_code == 200 and sub.json()["status"] == "submitted"

    # submitted reports stay intact across "refresh" (re-list)
    view = await client.get(f"/api/v1/learning/reports?student_id={w['student_id']}",
                            headers=auth(w["instructor"]))
    row = [x for x in view.json() if x["id"] == rid][0]
    assert row["status"] == "submitted"

    # instructor cannot edit a submitted report; admin can
    edit = await client.patch(f"/api/v1/learning/reports/{rid}",
                              json={"student_id": str(w["student_id"]),
                                    "enrollment_id": str(w["enrollment_id"]),
                                    "report_month": f"{Y}-{M:02d}",
                                    "strengths": "late change"},
                              headers=auth(w["instructor"]))
    assert edit.status_code == 403
    ok = await client.patch(f"/api/v1/learning/reports/{rid}",
                            json={"student_id": str(w["student_id"]),
                                  "enrollment_id": str(w["enrollment_id"]),
                                  "report_month": f"{Y}-{M:02d}",
                                  "strengths": "reviewed wording"},
                            headers=auth(w["admin"]))
    assert ok.status_code == 200

    # publishing is admin approval
    pub_deny = await client.post(f"/api/v1/learning/reports/{rid}/publish",
                                 headers=auth(w["instructor"]))
    assert pub_deny.status_code == 403
    pub = await client.post(f"/api/v1/learning/reports/{rid}/publish",
                            headers=auth(w["admin"]))
    assert pub.status_code == 200 and pub.json()["status"] == "published"

    # double-submit after publish is refused
    sub2 = await client.post(f"/api/v1/learning/reports/{rid}/submit",
                             headers=auth(w["instructor"]))
    assert sub2.status_code == 400


# ---------------------------------------------------------------------------
# 5. No duplicates — versions via revision only
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_one_report_per_month_revision_chain(client, with_records):
    w = with_records
    for _ in range(2):
        r = await client.post("/api/v1/learning/reports/generate-draft",
                              json={"enrollment_id": str(w["enrollment_id"]),
                                    "report_month": f"{Y}-{M:02d}",
                                    "confirm_overwrite": True},
                              headers=auth(w["instructor"]))
        assert r.status_code == 201
        assert r.json()["revision"] == 1      # same draft, no duplicate
    async with TestSessionLocal() as db:
        rows = (await db.execute(select(MonthlyReport).where(
            MonthlyReport.enrollment_id == w["enrollment_id"]))).scalars().all()
        assert len(rows) == 1

    # publish, then regenerate -> new revision, original intact
    rid = r.json()["id"]
    await client.post(f"/api/v1/learning/reports/{rid}/publish", headers=auth(w["admin"]))
    new_rev = await client.post("/api/v1/learning/reports/generate-draft",
                                json={"enrollment_id": str(w["enrollment_id"]),
                                      "report_month": f"{Y}-{M:02d}"},
                                headers=auth(w["instructor"]))
    assert new_rev.status_code == 201
    assert new_rev.json()["revision"] == 2
    assert new_rev.json()["status"] == "draft"
    async with TestSessionLocal() as db:
        rows = (await db.execute(select(MonthlyReport).where(
            MonthlyReport.enrollment_id == w["enrollment_id"]))).scalars().all()
        assert len(rows) == 2
        statuses = sorted(r.status for r in rows)
        assert statuses == ["draft", "published"]


# ---------------------------------------------------------------------------
# 6. Authorization: only the assigned instructor generates for the enrolment
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_unassigned_instructor_blocked(client, with_records):
    w = with_records
    r = await client.post("/api/v1/learning/reports/generate-draft",
                          json={"enrollment_id": str(w["enrollment_id"]),
                                "report_month": f"{Y}-{M:02d}"},
                          headers=auth(w["other"]))
    assert r.status_code == 403
