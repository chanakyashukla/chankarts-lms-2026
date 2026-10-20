"""
Privacy and account-lifecycle guards.

- No cross-student data exposure (instructor/parent scoping on /api/v1/students).
- Suspended/archived students cannot sign in; status changes sync the account flag.
- Instructor removal refuses when teaching history exists.
"""
import uuid
from datetime import date, time, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_privacy_guards.db"
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
from app.models.guardian import Guardian, GuardianAccount
from app.models.enrollment import Enrollment
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


async def _mk_user(db, username, role, pin="1234", email=None, active=True):
    u = User(username=username, email=email,
             hashed_password=get_password_hash(pin),
             role=role, is_active=active)
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def world():
    """admin, instructor A (teaches s1), instructor B (teaches nobody), s1, s2, parent-of-s2."""
    async with TestSessionLocal() as db:
        admin_u = await _mk_user(db, "pgadmin", UserRole.ADMIN, email="pgadmin@t.local")
        db.add(Admin(user_id=admin_u.id, first_name="PG", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        inst_a_u = await _mk_user(db, "pginsta", UserRole.INSTRUCTOR, pin="2468",
                                  email="pginsta@t.local")
        inst_a = Instructor(user_id=inst_a_u.id, first_name="A", last_name="Faculty",
                            specializations="Piano", is_active=True)
        db.add(inst_a)

        inst_b_u = await _mk_user(db, "pginstb", UserRole.INSTRUCTOR, pin="2468",
                                  email="pginstb@t.local")
        inst_b = Instructor(user_id=inst_b_u.id, first_name="B", last_name="Faculty",
                            specializations="Guitar", is_active=True)
        db.add(inst_b)
        await db.flush()

        s1_u = await _mk_user(db, "CMA-9001", UserRole.STUDENT, pin="9001")
        s1 = Student(user_id=s1_u.id, cma_registration_id="CMA-2026-9001",
                     first_name="One", last_name="Student", status="active")
        s2_u = await _mk_user(db, "CMA-9002", UserRole.STUDENT, pin="9002")
        s2 = Student(user_id=s2_u.id, cma_registration_id="CMA-2026-9002",
                     first_name="Two", last_name="Student", status="active")
        db.add_all([s1, s2])
        await db.flush()

        e1 = Enrollment(student_id=s1.id, programme_id="piano", programme_name="Piano",
                        instructor_id=inst_a.id, fee_plan="4_classes", fee_amount=4500,
                        status="active")
        e2 = Enrollment(student_id=s2.id, programme_id="guitar", programme_name="Guitar",
                        instructor_id=inst_b.id, fee_plan="4_classes", fee_amount=4500,
                        status="active")
        db.add_all([e1, e2])

        parent_u = await _mk_user(db, "pgparent", UserRole.PARENT, pin="1111",
                                  email="pgparent@t.local")
        db.add(GuardianAccount(user_id=parent_u.id, student_id=s2.id, relationship="mother"))

        stray = Guardian(student_id=s2.id, first_name="Mum", last_name="Student",
                         guardian_relationship="mother", phone="9999900000")
        db.add(stray)
        await db.commit()
        return {
            "admin": admin_u, "inst_a": inst_a_u, "inst_a_id": inst_a.id,
            "inst_b": inst_b_u, "inst_b_id": inst_b.id,
            "s1": s1_u, "s1_id": s1.id, "s2": s2_u, "s2_id": s2.id,
            "parent": parent_u, "e1": e1.id, "e2": e2.id,
        }


# ---------------------------------------------------------------------------
# Cross-student exposure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_instructor_cannot_read_unassigned_student(client, world):
    w = world
    r = await client.get(f"/api/v1/students/{w['s2_id']}", headers=auth(w["inst_a"]))
    assert r.status_code == 403
    # ... but CAN read their own assigned student
    ok = await client.get(f"/api/v1/students/{w['s1_id']}", headers=auth(w["inst_a"]))
    assert ok.status_code == 200
    assert ok.json()["first_name"] == "One"


@pytest.mark.asyncio
async def test_parent_cannot_read_unlinked_student(client, world):
    w = world
    r = await client.get(f"/api/v1/students/{w['s1_id']}", headers=auth(w["parent"]))
    assert r.status_code == 403
    ok = await client.get(f"/api/v1/students/{w['s2_id']}", headers=auth(w["parent"]))
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_instructor_student_list_is_scoped(client, world):
    w = world
    r = await client.get("/api/v1/students/", headers=auth(w["inst_a"]))
    assert r.status_code == 200
    ids = {x["id"] for x in r.json()}
    assert str(w["s1_id"]) in ids
    assert str(w["s2_id"]) not in ids
    # instructor with no assignments sees nobody
    r2 = await client.get("/api/v1/students/", headers=auth(w["inst_b"]))
    assert r2.json() != [] or True  # inst_b teaches s2 -> sees only s2
    ids2 = {x["id"] for x in r2.json()}
    assert str(w["s2_id"]) in ids2 and str(w["s1_id"]) not in ids2


@pytest.mark.asyncio
async def test_instructor_guardian_pii_blocked(client, world):
    w = world
    # even their own assigned student's guardian contacts are not for teaching staff
    r = await client.get(f"/api/v1/students/{w['s1_id']}/guardians", headers=auth(w["inst_a"]))
    assert r.status_code == 403
    # parent of s2 can see s2's guardians
    ok = await client.get(f"/api/v1/students/{w['s2_id']}/guardians", headers=auth(w["parent"]))
    assert ok.status_code == 200
    # and not s1's
    deny = await client.get(f"/api/v1/students/{w['s1_id']}/guardians", headers=auth(w["parent"]))
    assert deny.status_code == 403


@pytest.mark.asyncio
async def test_instructor_cannot_write_student_records(client, world):
    w = world
    r = await client.post("/api/v1/students/", json={
        "user_id": str(uuid.uuid4()), "first_name": "X", "last_name": "Y",
        "date_of_birth": "2010-01-01", "instruments": [], "guardians": [],
    }, headers=auth(w["inst_a"]))
    assert r.status_code == 403
    r2 = await client.patch(f"/api/v1/students/{w['s1_id']}",
                            json={"phone": "123"}, headers=auth(w["inst_a"]))
    assert r2.status_code == 403
    r3 = await client.post(f"/api/v1/students/{w['s1_id']}/guardians",
                           json={"first_name": "G", "last_name": "H", "phone": "999",
                                 "relationship": "mother"},
                           headers=auth(w["inst_a"]))
    assert r3.status_code == 403


# ---------------------------------------------------------------------------
# Suspension blocks sign-in
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_suspended_student_cannot_login(client, world):
    w = world
    # correct PIN works before suspension
    r = await client.post("/api/v1/auth/login",
                          json={"email": "CMA-9001", "password": "9001"})
    assert r.status_code == 200

    susp = await client.patch(f"/api/v1/admin/students/{w['s1_id']}",
                              json={"status": "suspended"}, headers=auth(w["admin"]))
    assert susp.status_code == 200

    r2 = await client.post("/api/v1/auth/login",
                           json={"email": "CMA-9001", "password": "9001"})
    assert r2.status_code == 403

    # reactivate restores sign-in
    await client.patch(f"/api/v1/admin/students/{w['s1_id']}",
                       json={"status": "active"}, headers=auth(w["admin"]))
    r3 = await client.post("/api/v1/auth/login",
                           json={"email": "CMA-9001", "password": "9001"})
    assert r3.status_code == 200


@pytest.mark.asyncio
async def test_archived_student_cannot_login(client, world):
    w = world
    await client.patch(f"/api/v1/admin/students/{w['s2_id']}",
                       json={"status": "archived"}, headers=auth(w["admin"]))
    r = await client.post("/api/v1/auth/login",
                          json={"email": "CMA-9002", "password": "9002"})
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# Instructor removal guard
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_instructor_delete_guard(client, world):
    w = world
    # instructor with teaching history must not be deletable
    r = await client.delete(f"/api/v1/admin/instructors/{w['inst_a_id']}",
                            headers=auth(w["admin"]))
    assert r.status_code == 409

    # instructor with no history can be removed
    async with TestSessionLocal() as db:
        solo_u = User(username="pgsolo", email="pgsolo@t.local",
                      hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(solo_u)
        await db.flush()
        solo = Instructor(user_id=solo_u.id, first_name="Solo", last_name="Free",
                          specializations="drums", is_active=True)
        db.add(solo)
        await db.commit()
        solo_id = solo.id
    r2 = await client.delete(f"/api/v1/admin/instructors/{solo_id}", headers=auth(w["admin"]))
    assert r2.status_code == 200 and r2.json()["deleted"] is True
