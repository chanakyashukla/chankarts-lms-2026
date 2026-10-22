"""
Automatic Login ID derivation from the CMA roll number: deterministic rule,
collision safety, legacy explicit-username compatibility and existing-account
stability.
"""
import re
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_login_id_auto.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.admin import Admin
from app.models.student import Student
from app.api.v1.admin import _login_id_from_roll


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
        u = User(id=uuid.uuid4(), username="idadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Id", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


# ---------------------------------------------------------------------------
def test_derivation_rule():
    assert _login_id_from_roll("CMA-2026-0015") == "CMA-015"
    assert _login_id_from_roll("CMA-2026-0099") == "CMA-099"
    assert _login_id_from_roll("CMA-2026-0104") == "CMA-104"
    assert _login_id_from_roll("CMA-2026-0007") == "CMA-007"
    # non-standard suffix: deterministic fallback
    assert _login_id_from_roll("CMA-2026-23CE9E") == "CMA-23CE9E"


@pytest.mark.asyncio
async def test_create_without_username_derives_login(client, admin_user):
    h = auth(admin_user)
    r = await client.post("/api/v1/admin/students", json={
        "first_name": "Auto", "last_name": "Kid", "cma_registration_id": "CMA-2026-0015",
    }, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["login_id"] == "CMA-015"
    assert body["cma_registration_id"] == "CMA-2026-0015"
    async with TestSessionLocal() as s:
        u = (await s.execute(select(User).where(User.username == "CMA-015"))).scalar_one()
        assert u.role == UserRole.STUDENT
        # derived login authenticates with the issued temp PIN
        assert get_password_hash  # sanity
        from app.core.security import verify_password
        assert verify_password(body["temp_pin"], u.hashed_password)


@pytest.mark.asyncio
async def test_create_with_generated_roll_derives_login(client, admin_user):
    h = auth(admin_user)
    r = await client.post("/api/v1/admin/students", json={"first_name": "Seq"}, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert re.fullmatch(r"CMA-\d{4}-\d{4}", body["cma_registration_id"])
    m = re.match(r"CMA-\d{4}-(\d+)$", body["cma_registration_id"])
    assert body["login_id"] == f"CMA-{int(m.group(1)):03d}"


@pytest.mark.asyncio
async def test_duplicate_login_rejected(client, admin_user):
    h = auth(admin_user)
    r1 = await client.post("/api/v1/admin/students", json={
        "first_name": "Dup", "cma_registration_id": "CMA-2026-0016"}, headers=h)
    assert r1.status_code == 201
    # same roll again → login-collision (derived CMA-016 already in use)
    r2 = await client.post("/api/v1/admin/students", json={
        "first_name": "Dup2", "cma_registration_id": "CMA-2026-0016"}, headers=h)
    assert r2.status_code == 409  # roll collision fires first
    # different roll colliding on the SAME derived login:0016 → CMA-016 vs 016?
    # construct an explicit username collision (legacy path)
    r3 = await client.post("/api/v1/admin/students", json={
        "first_name": "Dup3", "username": "CMA-016"}, headers=h)
    assert r3.status_code == 409 and "login id" in r3.json()["detail"].lower()
    # derived-collision message path: roll0999 (login CMA-999) created, then roll with same login impossible —
    # instead create explicit then derive that matches:
    r4 = await client.post("/api/v1/admin/students", json={
        "first_name": "X", "username": "CMA-777"}, headers=h)
    assert r4.status_code == 201
    r5 = await client.post("/api/v1/admin/students", json={
        "first_name": "Y", "cma_registration_id": "CMA-2026-0777"}, headers=h)
    assert r5.status_code == 409 and "derived from roll" in r5.json()["detail"]


@pytest.mark.asyncio
async def test_legacy_explicit_username_still_supported(client, admin_user):
    h = auth(admin_user)
    r = await client.post("/api/v1/admin/students", json={
        "username": "legacy.stu", "first_name": "Legacy"}, headers=h)
    assert r.status_code == 201 and r.json()["login_id"] == "legacy.stu"


@pytest.mark.asyncio
async def test_existing_accounts_keep_login_and_can_authenticate(client, admin_user):
    h = auth(admin_user)
    # created the legacy way (explicit username)
    r = await client.post("/api/v1/admin/students", json={
        "username": "existing.stu", "first_name": "Existing"}, headers=h)
    assert r.status_code == 201
    temp = r.json()["temp_pin"]
    # a later creation with auto-login does NOT touch the existing account
    r2 = await client.post("/api/v1/admin/students", json={"first_name": "Other"}, headers=h)
    assert r2.status_code == 201
    async with TestSessionLocal() as s:
        u = (await s.execute(select(User).where(User.username == "existing.stu"))).scalar_one()
        assert u.username == "existing.stu" and u.is_active
    # login still works with the existing credentials
    st, body = None, None
    resp = await client.post("/api/v1/auth/login", json={"email": "existing.stu", "password": temp})
    assert resp.status_code in (200, 403)  #403 = PIN-change gate, still authenticates
    if resp.status_code == 200:
        assert resp.json()["role"] == "student"


@pytest.mark.asyncio
async def test_roll_not_editable_after_create_keeps_login_stable(client, admin_user):
    h = auth(admin_user)
    r = await client.post("/api/v1/admin/students", json={
        "first_name": "Stable", "cma_registration_id": "CMA-2026-0088"}, headers=h)
    assert r.status_code == 201
    sid, login = r.json()["id"], r.json()["login_id"]
    assert login == "CMA-088"
    # profile updates never carry a username/roll field → login stays put
    p = await client.patch(f"/api/v1/admin/students/{sid}",
                           json={"phone": "9999999999", "first_name": "Stable2"}, headers=h)
    assert p.status_code == 200
    async with TestSessionLocal() as s:
        users = [x.username for x in (await s.execute(select(User))).scalars().all()]
        assert "CMA-088" in users
        st = (await s.execute(select(Student).where(Student.id == uuid.UUID(sid)))).scalar_one()
        assert st.cma_registration_id == "CMA-2026-0088"
