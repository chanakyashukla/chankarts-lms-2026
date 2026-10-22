"""
Instructor contact management: admin can add/edit email + phone; validation,
uniqueness, credential preservation and audit. Also covers the travel-buffer
field used by scheduling (0..600 minutes).
"""
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_instructor_contact.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.models.admin import Admin
from app.models.instructor import Instructor


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
        u = User(id=uuid.uuid4(), username="icadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Ic", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _mk_instructor(username: str, email=None) -> tuple[str, str]:
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=username, email=email,
                 hashed_password=get_password_hash("4321"), role=UserRole.INSTRUCTOR,
                 is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        i = Instructor(id=uuid.uuid4(), user_id=u.id, first_name="Teach", last_name="Er",
                       is_active=True)
        s.add(i)
        await s.commit()
        return str(i.id), str(u.id)


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_with_email_and_list_exposes_it(client, admin_user):
    h = auth(admin_user)
    r = await client.post("/api/v1/admin/instructors", json={
        "username": "mail.ins", "first_name": "Mail", "email": "Mail.INS@Example.com"},
        headers=h)
    assert r.status_code == 201, r.text
    lst = await client.get("/api/v1/admin/instructors", headers=h)
    row = next(x for x in lst.json() if x["login_id"] == "mail.ins")
    assert row["email"] == "mail.ins@example.com"   # stored lowercased


@pytest.mark.asyncio
async def test_edit_email_and_phone_persist(client, admin_user):
    h = auth(admin_user)
    iid, uid = await _mk_instructor("editme")
    r = await client.patch(f"/api/v1/admin/instructors/{iid}", json={
        "email": "new.address@example.com", "phone": "9876501234",
        "specializations": "Piano, Theory"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["email"] == "new.address@example.com"
    assert r.json()["phone"] == "9876501234"

    # survives refresh via the list endpoint
    lst = await client.get("/api/v1/admin/instructors", headers=h)
    row = next(x for x in lst.json() if x["id"] == iid)
    assert row["email"] == "new.address@example.com" and row["phone"] == "9876501234"
    assert row["specializations"] == "Piano, Theory"

    # stored on the account row; credentials untouched
    async with TestSessionLocal() as s:
        u = (await s.execute(select(User).where(User.id == uuid.UUID(uid)))).scalar_one()
        assert u.email == "new.address@example.com"
        assert verify_password("4321", u.hashed_password)
        assert u.username == "editme" and u.role == UserRole.INSTRUCTOR


@pytest.mark.asyncio
async def test_invalid_and_duplicate_email_rejected(client, admin_user):
    h = auth(admin_user)
    iid, _ = await _mk_instructor("validmail", email="taken@example.com")
    iid2, _ = await _mk_instructor("othermail")

    r = await client.patch(f"/api/v1/admin/instructors/{iid2}",
                           json={"email": "not-an-email"}, headers=h)
    assert r.status_code == 400 and "email" in r.json()["detail"].lower()

    r = await client.patch(f"/api/v1/admin/instructors/{iid2}",
                           json={"email": "taken@example.com"}, headers=h)
    assert r.status_code == 409 and "already in use" in r.json()["detail"]

    # clearing is allowed (optional schema)
    r = await client.patch(f"/api/v1/admin/instructors/{iid}",
                           json={"email": ""}, headers=h)
    assert r.status_code == 200
    async with TestSessionLocal() as s:
        rows = (await s.execute(select(User).where(User.email == "taken@example.com"))).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_email_change_does_not_touch_pin_or_create_accounts(client, admin_user):
    h = auth(admin_user)
    iid, uid = await _mk_instructor("keepauth")
    before_hash = None
    async with TestSessionLocal() as s:
        before_hash = (await s.execute(select(User.hashed_password).where(User.id == uuid.UUID(uid)))).scalar()
    r = await client.patch(f"/api/v1/admin/instructors/{iid}",
                           json={"email": "kept@example.com"}, headers=h)
    assert r.status_code == 200
    async with TestSessionLocal() as s:
        users = (await s.execute(select(User))).scalars().all()
        assert len(users) == 2   # admin + the single instructor — no extra accounts
        u = (await s.execute(select(User).where(User.id == uuid.UUID(uid)))).scalar_one()
        assert u.hashed_password == before_hash

    # audit recorded the edit
    from app.models.audit import AuditEvent
    async with TestSessionLocal() as s:
        events = (await s.execute(select(AuditEvent).where(
            AuditEvent.action == "instructor.updated"))).scalars().all()
        assert events and any("email" in (e.summary or "") for e in events)


@pytest.mark.asyncio
async def test_travel_buffer_field_validation(client, admin_user):
    h = auth(admin_user)
    iid, _ = await _mk_instructor("traveler")
    r = await client.patch(f"/api/v1/admin/instructors/{iid}",
                           json={"travel_buffer_minutes": 45}, headers=h)
    assert r.status_code == 200
    lst = await client.get("/api/v1/admin/instructors", headers=h)
    row = next(x for x in lst.json() if x["id"] == iid)
    assert row["travel_buffer_minutes"] == 45
    # bounds
    r = await client.patch(f"/api/v1/admin/instructors/{iid}",
                           json={"travel_buffer_minutes": 601}, headers=h)
    assert r.status_code == 400 and "Travel buffer" in r.json()["detail"]
    r = await client.patch(f"/api/v1/admin/instructors/{iid}",
                           json={"travel_buffer_minutes": -5}, headers=h)
    assert r.status_code == 400
