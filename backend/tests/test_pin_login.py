"""
PIN-login & private-LMS tests:
- public self-registration disabled (403)
- student login by Roll No. / Login ID + 4-digit PIN (hashed)
- forced PIN change on first login (server-side gate)
- wrong/invalid credentials rejected
- weekly timetable conflict detection (never auto-resolved)
- administrator PIN reset (one-time, hashed)
- student data isolation between accounts
"""
import re

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_pin_login.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.models.admin import Admin
from app.models.student import Student
from app.models.instructor import Instructor
from app.models.enrollment import Enrollment
from app.models.class_schedule import ClassSchedule
from datetime import date, time
from datetime import timedelta


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


async def _make_user(username, pin, role=UserRole.STUDENT, must_change=True):
    async with TestSessionLocal() as session:
        user = User(
            email=None,
            username=username,
            hashed_password=get_password_hash(pin),
            role=role,
            is_active=True,
            must_change_pin=must_change,
        )
        session.add(user)
        await session.flush()
        if role == UserRole.STUDENT:
            session.add(Student(
                user_id=user.id,
                cma_registration_id=f"CMA-2026-{username.split('-')[-1]}",
                portal_slug=username.lower(),
                first_name="Test",
                last_name="Student",
                date_of_birth=None,
                status="active",
                profile_complete=False,
            ))
        await session.commit()
        return user


@pytest_asyncio.fixture
async def student_user():
    return await _make_user("CMA-9001", "1234")


@pytest_asyncio.fixture
async def other_student():
    return await _make_user("CMA-9002", "5678")


@pytest_asyncio.fixture
async def admin_user():
    return await _make_user("test.admin", "AdminPass@123", role=UserRole.ADMIN, must_change=False)


# ---------------------------------------------------------------------------
# Public registration disabled
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_public_register_disabled(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "newbie@example.com",
        "username": "newbie",
        "password": "Whatever@123",
        "role": "student",
    })
    assert resp.status_code == 403
    assert "provisioned by the academy administrator" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Login by Roll No. + PIN, forced change, gate, invalid credentials
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_student_login_by_roll_with_pin(client, student_user):
    # Login with Roll No. as identifier + 4-digit PIN
    resp = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": "1234"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "student"
    assert body["must_change_pin"] is True
    token = body["access_token"]

    # Server-side gate: no data access until PIN changed
    blocked = await client.get("/api/v1/portal/me", headers={"Authorization": f"Bearer {token}"})
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "PIN_CHANGE_REQUIRED"

    # Bad-format new PIN rejected
    resp = await client.post("/api/v1/auth/change-pin",
        json={"current_pin": "1234", "new_pin": "12"},
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 400

    # Wrong current PIN rejected
    resp = await client.post("/api/v1/auth/change-pin",
        json={"current_pin": "9999", "new_pin": "5678"},
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401

    # Valid change
    resp = await client.post("/api/v1/auth/change-pin",
        json={"current_pin": "1234", "new_pin": "5678"},
        headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["must_change_pin"] is False

    # Gate lifted
    ok = await client.get("/api/v1/portal/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert ok.json()["role"] == "student"

    # Old PIN no longer works; new PIN does
    old = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": "1234"})
    assert old.status_code == 401
    new = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": "5678"})
    assert new.status_code == 200
    assert new.json()["must_change_pin"] is False


@pytest.mark.asyncio
async def test_invalid_credentials_rejected(client, student_user):
    # Wrong PIN
    resp = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": "9999"})
    assert resp.status_code == 401
    # Unknown roll
    resp = await client.post("/api/v1/auth/login", json={"email": "CMA-4040", "password": "1234"})
    assert resp.status_code == 401
    # Long password (not the PIN) cannot match a 4-digit PIN hash
    resp = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": "not-my-pin"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_pin_stored_as_hash(student_user):
    async with TestSessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.username == "CMA-9001"))).scalar_one()
        assert user.hashed_password != "1234"
        assert user.hashed_password.startswith("$2")  # bcrypt
        assert verify_password("1234", user.hashed_password)


# ---------------------------------------------------------------------------
# Student data isolation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_student_isolated_from_other_students(client, student_user, other_student):
    # Sign in as student 1
    login = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": "1234"})
    token = login.json()["access_token"]
    # Change PIN so gate lifts
    await client.post("/api/v1/auth/change-pin",
        json={"current_pin": "1234", "new_pin": "2222"},
        headers={"Authorization": f"Bearer {token}"})

    async with TestSessionLocal() as session:
        other = (await session.execute(
            select(Student).where(Student.user_id == other_student.id))).scalar_one()

    # Own portal OK
    own = await client.get("/api/v1/portal/me", headers={"Authorization": f"Bearer {token}"})
    assert own.status_code == 200
    assert own.json()["user_id"] == str(student_user.id)

    # Another student's records: 403
    foreign = await client.get(
        f"/api/v1/remarks?student_id={other.id}",
        headers={"Authorization": f"Bearer {token}"})
    assert foreign.status_code == 403


# ---------------------------------------------------------------------------
# Weekly timetable conflict detection (never auto-resolved)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_schedule_conflict_detected_not_resolved(client, admin_user, student_user, other_student):
    async with TestSessionLocal() as session:
        instr_user = User(
            email=None, username="test.faculty",
            hashed_password=get_password_hash("Fac@1234"),
            role=UserRole.INSTRUCTOR, is_active=True, must_change_pin=False,
        )
        session.add(instr_user)
        await session.flush()
        instr = Instructor(
            user_id=instr_user.id, first_name="Test", last_name="Faculty",
            specializations="piano", is_active=True,
        )
        session.add(instr)
        await session.flush()

        s1 = (await session.execute(
            select(Student).where(Student.user_id == student_user.id))).scalar_one()
        s2 = (await session.execute(
            select(Student).where(Student.user_id == other_student.id))).scalar_one()

        e1 = Enrollment(student_id=s1.id, programme_id="piano", programme_name="Piano",
                        status="active")
        e2 = Enrollment(student_id=s2.id, programme_id="piano", programme_name="Piano",
                        status="active")
        session.add_all([e1, e2])
        await session.flush()

        # Overlapping Friday 18:00-19:00 — both preserved exactly as entered
        session.add(ClassSchedule(enrollment_id=e1.id, instructor_id=instr.id,
                                  day_of_week="friday", start_time=time(18, 0),
                                  end_time=time(19, 0), frequency="weekly", is_active=True))
        session.add(ClassSchedule(enrollment_id=e2.id, instructor_id=instr.id,
                                  day_of_week="friday", start_time=time(18, 30),
                                  end_time=time(19, 30), frequency="weekly", is_active=True))
        await session.commit()

    resp = await client.get("/api/v1/admin/schedules", headers=auth(admin_user))
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["schedules"]) == 2  # neither class moved or dropped
    assert len(body["conflicts"]) == 1
    conflict = body["conflicts"][0]
    assert conflict["day_of_week"] == "friday"
    assert conflict["overlap_start"] == "18:30:00"
    assert conflict["overlap_end"] == "19:00:00"
    assert conflict["auto_resolved"] is False

    # Non-admin cannot see schedules
    denied = await client.get("/api/v1/admin/schedules", headers=auth(student_user))
    assert denied.status_code == 403


# ---------------------------------------------------------------------------
# Administrator PIN reset
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_reset_student_pin(client, admin_user, student_user):
    async with TestSessionLocal() as session:
        student = (await session.execute(
            select(Student).where(Student.user_id == student_user.id))).scalar_one()

    resp = await client.post(
        f"/api/v1/admin/students/{student.id}/reset-pin", headers=auth(admin_user))
    assert resp.status_code == 200
    body = resp.json()
    assert re.fullmatch(r"\d{4}", body["new_pin"])
    assert body["must_change_pin"] is True

    # New PIN logs in; old PIN does not
    old = await client.post("/api/v1/auth/login", json={"email": "CMA-9001", "password": "1234"})
    assert old.status_code == 401
    fresh = await client.post("/api/v1/auth/login",
        json={"email": "CMA-9001", "password": body["new_pin"]})
    assert fresh.status_code == 200
    assert fresh.json()["must_change_pin"] is True  # must change at next login

    # Stored as hash, never plaintext
    async with TestSessionLocal() as session:
        user = (await session.execute(
            select(User).where(User.username == "CMA-9001"))).scalar_one()
        assert user.hashed_password != body["new_pin"]
        assert verify_password(body["new_pin"], user.hashed_password)


@pytest.mark.asyncio
async def test_admin_login_still_works(client, admin_user):
    # Administrator account access (password-based) remains functional
    resp = await client.post("/api/v1/auth/login",
        json={"email": "test.admin", "password": "AdminPass@123"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
    assert resp.json()["must_change_pin"] is False
