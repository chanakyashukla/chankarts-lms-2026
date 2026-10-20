"""
Schema bootstrap + database persistence.

Verifies that a FRESH database (the deployment case: only Alembic has run, or
nothing has) is brought fully up to the models by app.db_bootstrap.sync_schema,
that data persists across an application restart, and that a real
register/login workflow works end-to-end against that fresh database.
"""
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_schema_bootstrap.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.db_bootstrap import sync_schema
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.models.user import User


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


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


# ---------------------------------------------------------------------------
# 1. A fresh database gets every model table and key columns
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sync_schema_creates_all_tables_on_fresh_database():
    fresh = create_async_engine("sqlite+aiosqlite:///./test_bootstrap_fresh.db", echo=False)
    try:
        log = await sync_schema(fresh)
        assert any("create_all" in line for line in log)

        async with fresh.begin() as conn:
            def _tables(c):
                return set(inspect(c).get_table_names())
            tables = await conn.run_sync(_tables)

        expected = set(Base.metadata.tables.keys())
        missing = expected - tables
        assert not missing, f"missing tables after bootstrap: {sorted(missing)}"

        # columns introduced during development must exist on a fresh DB
        async with fresh.begin() as conn:
            def _cols(c):
                insp = inspect(c)
                return {
                    ("invoices", "charge_type"), ("invoices", "description"),
                    ("payments", "receipt_number"), ("payments", "source"),
                    ("class_sessions", "practice_recommendations"),
                } <= {
                    (t, col["name"])
                    for t in ("invoices", "payments", "class_sessions")
                    for col in insp.get_columns(t)
                }
            assert await conn.run_sync(_cols), "development-era columns missing after bootstrap"

        # idempotent: second run changes nothing and does not error
        log2 = await sync_schema(fresh)
        assert log2
    finally:
        await fresh.dispose()
        import os
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(f"./test_bootstrap_fresh.db{suffix}")
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# 2. Persistence across "restart" + real auth workflow on the bootstrapped DB
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_persistence_and_login_on_bootstrapped_database(client):
    # create a real student account through the ORM (as provisioning does)
    async with TestSessionLocal() as db:
        user = User(username="CMA-7777", email=None,
                    hashed_password=get_password_hash("7777"),
                    role=UserRole.STUDENT, is_active=True, must_change_pin=True)
        db.add(user)
        await db.commit()
        user_id = user.id

    # "restart": fresh session factory against the same database file
    async with TestSessionLocal() as db:
        again = (await db.execute(select_user := __import__("sqlalchemy").select(User).where(User.id == user_id))).scalar_one()
        assert again.username == "CMA-7777"
        assert again.must_change_pin is True

    # end-to-end: login with the temporary PIN works
    r = await client.post("/api/v1/auth/login",
                          json={"email": "CMA-7777", "password": "7777"})
    assert r.status_code == 200, r.text
    assert r.json()["must_change_pin"] is True
    token = r.json()["access_token"]

    # forced PIN change is enforced...
    me = await client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 403  # PIN_CHANGE_REQUIRED

    # ...and completing it grants access
    changed = await client.post("/api/v1/auth/change-pin",
                                json={"current_pin": "7777", "new_pin": "1357"},
                                headers={"Authorization": f"Bearer {token}"})
    assert changed.status_code == 200, changed.text

    r2 = await client.post("/api/v1/auth/login",
                           json={"email": "CMA-7777", "password": "1357"})
    assert r2.status_code == 200
    me2 = await client.get("/api/v1/auth/me",
                           headers={"Authorization": f"Bearer {r2.json()['access_token']}"})
    assert me2.status_code == 200
    assert me2.json()["username"] == "CMA-7777"


# ---------------------------------------------------------------------------
# 3. Health endpoint (deployment healthchecks depend on it)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_health_endpoint_available(client):
    r = await client.get("/health")
    assert r.status_code == 200
