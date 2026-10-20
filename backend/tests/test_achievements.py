"""
Student achievements showcase.

- Admin creates/verifies/archives achievement records.
- The student and their linked parent see verified achievements.
- Other students cannot see them (API-level enforcement).
- Historical achievements can be recorded without inventing results.
"""
import io
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_achievements.db"
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
from app.models.guardian import GuardianAccount
from app.models.enrollment import Enrollment


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
        admin_u = User(username="achadmin", email="achadmin@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="Ach", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        inst_u = User(username="achinst", email="achinst@t.local",
                      hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(inst_u)
        await db.flush()
        inst = Instructor(user_id=inst_u.id, first_name="Ach", last_name="Faculty",
                          specializations="piano", is_active=True)
        db.add(inst)

        sa_u = User(username="CMA-9501", hashed_password=get_password_hash("9501"),
                    role=UserRole.STUDENT)
        sb_u = User(username="CMA-9502", hashed_password=get_password_hash("9502"),
                    role=UserRole.STUDENT)
        db.add_all([sa_u, sb_u])
        await db.flush()
        sa = Student(user_id=sa_u.id, cma_registration_id="CMA-2026-9501",
                     first_name="Tal", last_name="Ented", status="active")
        sb = Student(user_id=sb_u.id, cma_registration_id="CMA-2026-9502",
                     first_name="Oth", last_name="Er", status="active")
        db.add_all([sa, sb])
        await db.flush()
        db.add(Enrollment(student_id=sa.id, programme_id="piano", programme_name="Piano",
                          instructor_id=inst.id, fee_plan="4_classes", fee_amount=4500,
                          status="active"))

        parent_u = User(username="achparent", email="achparent@t.local",
                        hashed_password=get_password_hash("x"), role=UserRole.PARENT)
        db.add(parent_u)
        await db.flush()
        db.add(GuardianAccount(user_id=parent_u.id, student_id=sa.id, relationship="mother"))
        await db.commit()
        return {"admin": admin_u, "instructor": inst_u,
                "student_a": sa_u, "sa_id": sa.id,
                "student_b": sb_u, "sb_id": sb.id, "parent": parent_u}


async def _create(client, w, **over):
    payload = {
        "student_id": str(w["sa_id"]),
        "title": "Trinity Grade 1 Piano",
        "category": "exam",
        "awarding_body": "Trinity College London",
        "programme_id": "piano",
        "grade_level": "Grade 1",
        "result": "Distinction",
        "achieved_on": "2026-06-15",
    }
    payload.update(over)
    r = await client.post("/api/v1/admin/achievements", json=payload, headers=auth(w["admin"]))
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Admin creates + verifies; student and parent see it
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_verified_achievement_visible_to_student_and_parent(client, world):
    w = world
    a = await _create(client, w)
    assert a["is_verified"] is False

    # invisible until verified
    before = await client.get(f"/api/v1/portal/achievements?student_id={w['sa_id']}",
                              headers=auth(w["student_a"]))
    assert before.json() == []

    v = await client.patch(f"/api/v1/admin/achievements/{a['id']}",
                           json={"is_verified": True}, headers=auth(w["admin"]))
    assert v.status_code == 200 and v.json()["is_verified"] is True

    stu = await client.get(f"/api/v1/portal/achievements?student_id={w['sa_id']}",
                           headers=auth(w["student_a"]))
    assert len(stu.json()) == 1
    row = stu.json()[0]
    assert row["title"] == "Trinity Grade 1 Piano"
    assert row["result"] == "Distinction"

    par = await client.get(f"/api/v1/portal/achievements?student_id={w['sa_id']}",
                           headers=auth(w["parent"]))
    assert len(par.json()) == 1

    inst = await client.get(f"/api/v1/portal/achievements?student_id={w['sa_id']}",
                            headers=auth(w["instructor"]))
    assert len(inst.json()) == 1


# ---------------------------------------------------------------------------
# Other students cannot see it — API level
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_other_students_cannot_see_achievements(client, world):
    w = world
    a = await _create(client, w, is_verified=True)
    await client.patch(f"/api/v1/admin/achievements/{a['id']}",
                       json={"is_verified": True}, headers=auth(w["admin"]))

    r = await client.get(f"/api/v1/portal/achievements?student_id={w['sa_id']}",
                         headers=auth(w["student_b"]))
    assert r.status_code == 403

    # student B's own list is empty
    own = await client.get(f"/api/v1/portal/achievements?student_id={w['sb_id']}",
                           headers=auth(w["student_b"]))
    assert own.json() == []


# ---------------------------------------------------------------------------
# Historical achievements allowed; archive removes from view
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_historical_entry_and_archive(client, world):
    w = world
    a = await _create(client, w,
                      title="Grade 3 Piano (2019 cohort)",
                      achieved_on="2019-11-20", result="Merit")
    await client.patch(f"/api/v1/admin/achievements/{a['id']}",
                       json={"is_verified": True}, headers=auth(w["admin"]))
    seen = await client.get(f"/api/v1/portal/achievements?student_id={w['sa_id']}",
                            headers=auth(w["student_a"]))
    assert seen.json()[0]["achieved_on"] == "2019-11-20"

    arch = await client.patch(f"/api/v1/admin/achievements/{a['id']}",
                              json={"is_archived": True}, headers=auth(w["admin"]))
    assert arch.status_code == 200
    after = await client.get(f"/api/v1/portal/achievements?student_id={w['sa_id']}",
                             headers=auth(w["student_a"]))
    assert after.json() == []


# ---------------------------------------------------------------------------
# Certificate upload is type-validated and stays private
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_certificate_upload_validated_and_private(client, world):
    w = world
    a = await _create(client, w)

    bad = await client.post(
        f"/api/v1/admin/achievements/{a['id']}/certificate",
        files={"file": ("run.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
        headers=auth(w["admin"]))
    assert bad.status_code == 400

    good = await client.post(
        f"/api/v1/admin/achievements/{a['id']}/certificate",
        files={"file": ("cert.pdf", io.BytesIO(b"%PDF-1.4 ok"), "application/pdf")},
        headers=auth(w["admin"]))
    assert good.status_code == 201, good.text

    await client.patch(f"/api/v1/admin/achievements/{a['id']}",
                       json={"is_verified": True}, headers=auth(w["admin"]))
    seen = await client.get(f"/api/v1/portal/achievements?student_id={w['sa_id']}",
                            headers=auth(w["student_a"]))
    stored = seen.json()[0]["certificate"]["stored_name"]

    # owner can fetch; unrelated student cannot
    ok = await client.get(
        f"/api/v1/portal/achievements/files/{stored}?student_id={w['sa_id']}",
        headers=auth(w["student_a"]))
    assert ok.status_code == 200
    deny = await client.get(
        f"/api/v1/portal/achievements/files/{stored}?student_id={w['sa_id']}",
        headers=auth(w["student_b"]))
    assert deny.status_code == 403
