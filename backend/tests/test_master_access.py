"""
Master access — an administrator opens a student's portal (view-as).

- Only an admin can mint the session; instructors/students cannot.
- The session is short-lived and marked with an `imp` claim.
- It reads the student's portal data even while the student still has a
  temporary PIN pending (first login not completed).
- It can NEVER change the student's PIN — the change-pin endpoint refuses it
  and the stored hash stays untouched.
- Every mint is written to the audit trail.
- The session cannot reach admin APIs (it carries the student's role).
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_master_access.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash, decode_access_token, verify_password
from app.models.user import User
from app.models.admin import Admin
from app.models.student import Student
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


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _token(user: User) -> str:
    return create_access_token(data={"sub": str(user.id), "role": user.role.value})


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {_token(user)}"}


@pytest_asyncio.fixture
async def world():
    async with TestSessionLocal() as db:
        admin_u = User(username="madmin", email="madmin@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="Master", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        inst_u = User(username="minst", email="minst@t.local",
                      hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(inst_u)
        await db.flush()

        # temporary PIN still pending — the classic "student never logged in" case
        stu_u = User(username="CMA-9601", hashed_password=get_password_hash("1234"),
                     role=UserRole.STUDENT, must_change_pin=True)
        db.add(stu_u)
        await db.flush()
        stu = Student(user_id=stu_u.id, cma_registration_id="CMA-2026-9601",
                      first_name="Siri", last_name="Hosangadi", status="active")
        db.add(stu)
        await db.commit()
        return {"admin": admin_u, "instructor": inst_u, "student": stu_u, "student_obj": stu}


async def _mint(client, w, student_id=None, headers=None):
    sid = student_id or str(w["student_obj"].id)
    return await client.post(f"/api/v1/admin/students/{sid}/portal-session",
                             json={}, headers=headers or auth(w["admin"]))


@pytest.mark.asyncio
async def test_admin_mints_master_session_and_reads_portal(client, world):
    w = world
    r = await _mint(client, w)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["student_name"] == "Siri Hosangadi"
    assert body["expires_in"] == 15 * 60
    payload = decode_access_token(body["access_token"])
    assert payload["imp"] == str(w["admin"].id)          # marked as view-as
    assert payload["role"] == "student"                  # carries the student's role

    # the session sees the portal even though the student's PIN is pending
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    me = await client.get("/api/v1/portal/me", headers=headers)
    assert me.status_code == 200, me.text
    assert me.json()["role"] == "student"

    # ...but never reaches admin APIs
    admin_only = await client.get("/api/v1/admin/students", headers=headers)
    assert admin_only.status_code == 403


@pytest.mark.asyncio
async def test_master_session_is_audited(client, world):
    w = world
    await _mint(client, w)
    async with TestSessionLocal() as db:
        event = (await db.execute(
            select(AuditEvent).where(AuditEvent.action == "admin.portal_view_as")
        )).scalars().first()
        assert event is not None
        assert event.actor_user_id == w["admin"].id
        assert "Siri Hosangadi" in (event.summary or "")


@pytest.mark.asyncio
async def test_master_session_can_never_change_a_pin(client, world):
    w = world
    minted = (await _mint(client, w)).json()
    headers = {"Authorization": f"Bearer {minted['access_token']}"}

    r = await client.post("/api/v1/auth/change-pin", json={"current_pin": "1234", "new_pin": "9999"},
                          headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "MASTER_ACCESS_NO_PIN_CHANGE"

    # the student's own credential is untouched
    async with TestSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == w["student"].id))).scalar_one()
        assert verify_password("1234", user.hashed_password)   # original PIN still works
        assert user.must_change_pin is True


@pytest.mark.asyncio
async def test_only_admins_can_mint_master_sessions(client, world):
    w = world
    sid = str(w["student_obj"].id)

    as_instructor = await _mint(client, w, headers=auth(w["instructor"]))
    assert as_instructor.status_code == 403

    as_student = await _mint(client, w, headers=auth(w["student"]))
    assert as_student.status_code == 403

    anon = await client.post(f"/api/v1/admin/students/{sid}/portal-session", json={})
    assert anon.status_code in (401, 403)


@pytest.mark.asyncio
async def test_master_session_does_not_touch_student_login(client, world):
    """Minting a session must not alter the student's PIN or first-login flag."""
    w = world
    await _mint(client, w)
    async with TestSessionLocal() as db:
        user = (await db.execute(select(User).where(User.id == w["student"].id))).scalar_one()
        assert verify_password("1234", user.hashed_password)   # original PIN still works
        assert user.must_change_pin is True
