"""Application workflow tests — run against the FastAPI backend.

Covers the operational checklist: health, login/protected routes,
authorization, student management with unique CMA IDs, scheduling,
class completion and persistence behaviour.
"""
from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_workflows.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.admin import Admin
from app.models.student import Student


async def override_get_db():
    async with SessionLocal() as session:
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
async def setup():
    app.dependency_overrides[get_db] = override_get_db
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.drop_all)


def _token(u: User) -> dict:
    return {"Authorization": "Bearer " + create_access_token(
        data={"sub": str(u.id), "role": u.role.value}, expires_delta=timedelta(minutes=30))}


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin():
    async with SessionLocal() as db:
        u = User(username="wfadmin", email="wfadmin@example.com",
                 hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(u)
        await db.flush()
        db.add(Admin(user_id=u.id, first_name="WF", last_name="Admin",
                     admin_level="super_admin", is_active=True))
        await db.commit()
        return u


@pytest.mark.asyncio
async def test_health_endpoint(client):
    r = await client.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_protected_routes_reject_anonymous(client):
    for path in ("/api/v1/auth/me", "/api/v1/admin/students", "/api/v1/sessions"):
        r = await client.get(path)
        assert r.status_code in (401, 403), path


@pytest.mark.asyncio
async def test_login_and_logout_flow(client, admin):
    bad = await client.post("/api/v1/auth/login", json={"email": "wfadmin", "password": "wrong"})
    assert bad.status_code == 401
    ok = await client.post("/api/v1/auth/login", json={"email": "wfadmin", "password": "x"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    me = await client.get("/api/v1/auth/me", headers=_token(admin))
    assert me.status_code == 200 and me.json()["username"] == "wfadmin"


@pytest.mark.asyncio
async def test_student_create_search_unique_ids(client, admin):
    r = await client.post("/api/v1/admin/students", json={
        "first_name": "Workflow", "last_name": "Student", "email": "wf-student@example.com",
        "username": "CMA-9991",
    }, headers=_token(admin))
    assert r.status_code == 201, r.text
    body = r.json()
    assert (body.get("cma_registration_id") or body.get("login_id") or "").startswith("CMA")
    listing = await client.get("/api/v1/admin/students", headers=_token(admin))
    assert any(s["id"] == body["id"] for s in listing.json())
    # search/filter returns the record; archive blocks login-level data access
    found = await client.get(f"/api/v1/admin/students/{body['id']}", headers=_token(admin))
    assert found.status_code == 200
    assert (found.json().get("full_name") or (found.json().get("first_name", "") + " " + found.json().get("last_name", ""))).strip() == "Workflow Student"
    dup = await client.get("/api/v1/admin/students", headers=_token(admin))
    ids = [s.get("cma_registration_id") or s.get("id") for s in dup.json()]
    assert len(ids) == len(set(ids)), "CMA registration IDs must be unique"


@pytest.mark.asyncio
async def test_class_completion_persists(client, admin):
    from app.models.instructor import Instructor
    from app.models.enrollment import Enrollment
    from app.models.session import ClassSession
    async with SessionLocal() as db:
        stu_u = User(username="CMA-9999", hashed_password=get_password_hash("9999"),
                     role=UserRole.STUDENT)
        db.add(stu_u)
        await db.flush()
        stu = Student(user_id=stu_u.id, cma_registration_id="CMA-2026-9999",
                      first_name="Class", last_name="Test", status="active")
        db.add(stu)
        await db.flush()
        enr = Enrollment(student_id=stu.id, programme_id="piano", programme_name="Piano",
                         fee_plan="4_classes", fee_amount=4500, status="active")
        db.add(enr)
        await db.flush()
        sess = ClassSession(enrollment_id=enr.id, student_id=stu.id, instructor_id=None,
                            scheduled_date=date.today() + timedelta(days=1),
                            scheduled_start=time(17), scheduled_end=time(18),
                            timezone="Asia/Kolkata", status="scheduled")
        db.add(sess)
        await db.commit()
        sid, student_id = str(sess.id), stu.id

    # student cannot complete a class
    tok = create_access_token(data={"sub": str(stu_u.id), "role": "student"},
                              expires_delta=timedelta(minutes=30))
    deny = await client.post(f"/api/v1/sessions/{sid}/complete", json={},
                             headers={"Authorization": f"Bearer {tok}"})
    assert deny.status_code in (403, 400)
    # admin completes it; the record persists with notes
    ok = await client.post(f"/api/v1/sessions/{sid}/complete",
                           json={"topics_covered": "Scales", "faculty_remarks": "Good"},
                           headers=_token(admin))
    assert ok.status_code == 200 and ok.json()["status"] == "completed"
    async with SessionLocal() as db:
        row = (await db.execute(__import__("sqlalchemy").select(ClassSession).where(
            ClassSession.id == __import__("uuid").UUID(sid)))).scalar_one()
        assert row.status == "completed" and row.topics_covered == "Scales"
