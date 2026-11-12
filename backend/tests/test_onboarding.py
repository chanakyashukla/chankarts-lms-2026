"""
Interactive onboarding / guided-tour state tests (spec §1.C, §6, §7):
- GET returns a complete default state for a fresh account
- PUT persists shown / started / completed / skipped / progress / version
- explicit null clears a field (progress on completion), omitted fields stay
- state is self-scoped: one account can never read or write another's record
- PIN-change gate applies to onboarding reads until the PIN is changed
- wrong-role (unauthenticated) access is rejected
- validation rejects malformed progress payloads
"""
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_onboarding.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.student import Student


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


async def _make_user(username, pin, role=UserRole.STUDENT, must_change=False):
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
                first_name="Tour",
                last_name="Tester",
                date_of_birth=None,
                status="active",
                profile_complete=False,
            ))
        await session.commit()
        return user


@pytest_asyncio.fixture
async def student_user():
    return await _make_user("CMA-7001", "1234")


@pytest_asyncio.fixture
async def other_student():
    return await _make_user("CMA-7002", "5678")


@pytest_asyncio.fixture
async def instructor_user():
    return await _make_user("tour.instructor", "9012", role=UserRole.INSTRUCTOR)


@pytest_asyncio.fixture
async def gated_user():
    """A freshly provisioned account that must change its PIN first."""
    return await _make_user("CMA-7003", "3456", must_change=True)


# ---------------------------------------------------------------------------
# Fresh state
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fresh_account_gets_default_state(client, student_user):
    resp = await client.get("/api/v1/onboarding", headers=auth(student_user))
    assert resp.status_code == 200
    state = resp.json()
    assert state["shown"] is False
    assert state["started"] is False
    assert state["completed"] is False
    assert state["skipped"] is False
    assert state["progress"] is None
    assert state["version"]  # content version present
    assert state["updated_at"] is None


# ---------------------------------------------------------------------------
# Persisting the first-login flow
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_full_flow_persists_and_reads_back(client, student_user):
    headers = auth(student_user)

    # welcome intro displayed
    resp = await client.put("/api/v1/onboarding", json={"shown": True}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["shown"] is True
    assert resp.json()["updated_at"]

    # tour started, progress recorded step by step
    resp = await client.put("/api/v1/onboarding", json={
        "started": True,
        "progress": {"step": 2, "tour": "student"},
    }, headers=headers)
    body = resp.json()
    assert body["started"] is True
    assert body["shown"] is True          # earlier field untouched
    assert body["progress"] == {"step": 2, "tour": "student"}

    # interrupted mid-tour → resume info survives a fresh read
    resp = await client.get("/api/v1/onboarding", headers=headers)
    assert resp.json()["progress"]["step"] == 2

    # finish: completed, progress cleared with explicit null
    resp = await client.put("/api/v1/onboarding", json={
        "completed": True,
        "progress": None,
    }, headers=headers)
    body = resp.json()
    assert body["completed"] is True
    assert body["progress"] is None
    assert body["started"] is True
    assert body["shown"] is True


@pytest.mark.asyncio
async def test_skip_is_recorded_and_persistent(client, student_user):
    headers = auth(student_user)
    resp = await client.put("/api/v1/onboarding", json={
        "shown": True, "skipped": True,
    }, headers=headers)
    assert resp.json()["skipped"] is True

    resp = await client.get("/api/v1/onboarding", headers=headers)
    assert resp.json()["skipped"] is True
    assert resp.json()["completed"] is False


@pytest.mark.asyncio
async def test_omitted_fields_are_untouched(client, student_user):
    headers = auth(student_user)
    await client.put("/api/v1/onboarding", json={
        "shown": True, "started": True, "skipped": True,
    }, headers=headers)
    # a later partial write must not clear earlier decisions
    resp = await client.put("/api/v1/onboarding", json={
        "progress": {"step": 5, "tour": "student"},
    }, headers=headers)
    body = resp.json()
    assert body["shown"] is True
    assert body["started"] is True
    assert body["skipped"] is True
    assert body["progress"]["step"] == 5


# ---------------------------------------------------------------------------
# Self-scoping: one account can never touch another's state
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_state_is_per_account(client, student_user, other_student):
    await client.put("/api/v1/onboarding", json={
        "shown": True, "started": True, "completed": True,
    }, headers=auth(student_user))

    # the other account still sees its own untouched defaults
    resp = await client.get("/api/v1/onboarding", headers=auth(other_student))
    body = resp.json()
    assert body["shown"] is False
    assert body["completed"] is False

    # even a payload that tries to name another user only ever writes self
    resp = await client.put("/api/v1/onboarding", json={
        "shown": True, "user_id": "not-even-a-field",
    }, headers=auth(other_student))
    assert resp.status_code == 200
    assert resp.json()["shown"] is True

    resp = await client.get("/api/v1/onboarding", headers=auth(student_user))
    assert resp.json()["completed"] is True  # untouched by the other write


@pytest.mark.asyncio
async def test_requires_authentication(client, student_user):
    resp = await client.get("/api/v1/onboarding")
    assert resp.status_code in (401, 403)
    resp = await client.put("/api/v1/onboarding", json={"shown": True})
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# First-login ordering: PIN gate applies before tour state is reachable
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_pin_gate_blocks_onboarding_until_pin_changed(client, gated_user):
    headers = auth(gated_user)

    resp = await client.get("/api/v1/onboarding", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["detail"] == "PIN_CHANGE_REQUIRED"

    # complete the mandatory PIN change, then onboarding is reachable
    resp = await client.post("/api/v1/auth/change-pin", json={
        "current_pin": "3456", "new_pin": "7788",
    }, headers=headers)
    assert resp.status_code == 200

    resp = await client.get("/api/v1/onboarding", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["shown"] is False


# ---------------------------------------------------------------------------
# Role coverage: instructors get the same self-scoped surface
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_instructor_can_persist_own_state(client, instructor_user):
    headers = auth(instructor_user)
    resp = await client.put("/api/v1/onboarding", json={
        "shown": True, "started": True,
        "progress": {"step": 1, "tour": "instructor"},
    }, headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["progress"] == {"step": 1, "tour": "instructor"}

    resp = await client.get("/api/v1/onboarding", headers=headers)
    assert resp.json()["started"] is True


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rejects_malformed_progress(client, student_user):
    headers = auth(student_user)
    resp = await client.put("/api/v1/onboarding", json={
        "progress": {"step": -3},
    }, headers=headers)
    assert resp.status_code == 422

    resp = await client.put("/api/v1/onboarding", json={
        "progress": {"step": "two"},
    }, headers=headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejects_non_boolean_flags(client, student_user):
    resp = await client.put("/api/v1/onboarding", json={
        "shown": "yes-please",
    }, headers=auth(student_user))
    assert resp.status_code == 422
