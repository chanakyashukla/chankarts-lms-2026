"""
Tests for admin seeding and access control.
Verifies:
- Admin user can be seeded via env vars
- Admin login returns correct role
- Admin can access dashboard and registration requests
- Student/Instructor cannot access admin endpoints
"""
import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from unittest.mock import patch

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_admin_seed.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.models.user import User
from app.models.admin import Admin
from app.models.registration_request import RegistrationRequest
from app.core.roles import UserRole
from app.core.security import get_password_hash, create_access_token


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
async def seed_admin_user():
    """Create an admin user for tests."""
    async with TestSessionLocal() as session:
        user = User(
            id=uuid.uuid4(),
            email="admin@test.com",
            username="admintest",
            hashed_password=get_password_hash("TestPass@123"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.flush()

        admin = Admin(
            id=uuid.uuid4(),
            user_id=user.id,
            first_name="Test",
            last_name="Admin",
            admin_level="super_admin",
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        return user


@pytest_asyncio.fixture
async def student_user():
    """Create a student user for access control tests."""
    async with TestSessionLocal() as session:
        user = User(
            id=uuid.uuid4(),
            email="student@test.com",
            username="studenttest",
            hashed_password=get_password_hash("StudentPass@123"),
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        return user


@pytest_asyncio.fixture
async def instructor_user():
    """Create an instructor user for access control tests."""
    async with TestSessionLocal() as session:
        user = User(
            id=uuid.uuid4(),
            email="instructor@test.com",
            username="instructortest",
            hashed_password=get_password_hash("InstructorPass@123"),
            role=UserRole.INSTRUCTOR,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        return user


def make_token(user: User) -> str:
    return create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=timedelta(minutes=30),
    )


# ========================================
# Admin Seeding
# ========================================
@pytest.mark.asyncio
async def test_seed_admin_creates_user():
    """Seed function creates User + Admin when env vars are set."""
    from app.core.seed import seed_admin
    from app.config import get_settings

    with patch.dict("os.environ", {
        "SEED_ADMIN_EMAIL": "seeded@test.com",
        "SEED_ADMIN_USERNAME": "seededadmin",
        "SEED_ADMIN_PASSWORD": "SeedPass@123",
        "SEED_ADMIN_FIRST_NAME": "Seeded",
        "SEED_ADMIN_LAST_NAME": "Admin",
    }):
        get_settings.cache_clear()
        try:
            async with TestSessionLocal() as session:
                await seed_admin(session)
                await session.commit()

            async with TestSessionLocal() as session:
                result = await session.execute(select(User).where(User.email == "seeded@test.com"))
                user = result.scalar_one_or_none()
                assert user is not None
                assert user.role == UserRole.ADMIN
                assert user.is_active is True

                result2 = await session.execute(select(Admin).where(Admin.user_id == user.id))
                admin = result2.scalar_one_or_none()
                assert admin is not None
                assert admin.first_name == "Seeded"
                assert admin.admin_level == "super_admin"
        finally:
            get_settings.cache_clear()


@pytest.mark.asyncio
async def test_seed_admin_idempotent():
    """Seeding twice does not create duplicate users."""
    from app.core.seed import seed_admin
    from app.config import get_settings

    with patch.dict("os.environ", {
        "SEED_ADMIN_EMAIL": "idempotent@test.com",
        "SEED_ADMIN_USERNAME": "idempotentadmin",
        "SEED_ADMIN_PASSWORD": "IdemPass@123",
        "SEED_ADMIN_FIRST_NAME": "Idem",
        "SEED_ADMIN_LAST_NAME": "Admin",
    }):
        get_settings.cache_clear()
        try:
            async with TestSessionLocal() as session:
                await seed_admin(session)
                await session.commit()

            async with TestSessionLocal() as session:
                await seed_admin(session)
                await session.commit()

            async with TestSessionLocal() as session:
                from sqlalchemy import func
                result = await session.execute(
                    select(func.count(User.id)).where(User.email == "idempotent@test.com")
                )
                count = result.scalar()
                assert count == 1
        finally:
            get_settings.cache_clear()


@pytest.mark.asyncio
async def test_seed_admin_skips_when_env_not_set():
    """Seed function is a no-op when env vars are empty."""
    from app.core.seed import seed_admin
    from app.config import get_settings

    with patch.dict("os.environ", {
        "SEED_ADMIN_EMAIL": "",
        "SEED_ADMIN_USERNAME": "",
        "SEED_ADMIN_PASSWORD": "",
    }):
        get_settings.cache_clear()
        try:
            async with TestSessionLocal() as session:
                await seed_admin(session)
                await session.commit()

            async with TestSessionLocal() as session:
                from sqlalchemy import func
                result = await session.execute(select(func.count(User.id)))
                count = result.scalar()
                assert count == 0
        finally:
            get_settings.cache_clear()


# ========================================
# Admin Login
# ========================================
@pytest.mark.asyncio
async def test_admin_login_returns_admin_role(seed_admin_user):
    """Admin login returns token with role=admin."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            params={"email": "admin@test.com", "password": "TestPass@123"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["role"] == "admin"
    assert data["token_type"] == "bearer"
    assert data["user_id"] is not None


@pytest.mark.asyncio
async def test_admin_login_rejects_wrong_password(seed_admin_user):
    """Login with wrong password returns 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/login",
            params={"email": "admin@test.com", "password": "WrongPassword"},
        )
    assert response.status_code == 401


# ========================================
# Admin Dashboard Access
# ========================================
@pytest.mark.asyncio
async def test_admin_can_access_dashboard_stats(seed_admin_user):
    """Admin can access /admin/dashboard/stats."""
    token = make_token(seed_admin_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/dashboard/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert "total_students" in data
    assert "pending_registrations" in data


@pytest.mark.asyncio
async def test_student_cannot_access_admin_dashboard(student_user):
    """Student gets 403 on admin dashboard."""
    token = make_token(student_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/dashboard/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_instructor_cannot_access_admin_dashboard(instructor_user):
    """Instructor gets 403 on admin dashboard."""
    token = make_token(instructor_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/dashboard/stats",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_admin_dashboard():
    """No token returns 401/403."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/dashboard/stats")
    assert response.status_code in (401, 403)


# ========================================
# Registration Requests Access
# ========================================
@pytest.mark.asyncio
async def test_admin_can_list_registration_requests(seed_admin_user):
    """Admin can access GET /admin/registration-requests."""
    token = make_token(seed_admin_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/registration-requests",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_student_cannot_access_registration_requests(student_user):
    """Student gets 403 on registration requests list."""
    token = make_token(student_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/registration-requests",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_instructor_cannot_access_registration_requests(instructor_user):
    """Instructor gets 403 on registration requests list."""
    token = make_token(instructor_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/registration-requests",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_registration_requests():
    """No token returns 401/403 on registration requests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/registration-requests")
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_can_update_registration_status(seed_admin_user):
    """Admin can PATCH /admin/registration-requests/:id/status."""
    async with TestSessionLocal() as session:
        reg = RegistrationRequest(
            id=uuid.uuid4(),
            request_id="REQ-2026-0001",
            full_name="Test Student",
            email="teststudent@test.com",
            mobile="9999999999",
            date_of_birth=datetime(2000, 1, 1).date(),
            is_minor=False,
            selected_programmes=["piano"],
            status="email_verified",
            submitted_at=datetime.utcnow(),
            review_deadline=datetime.utcnow() + timedelta(hours=72),
        )
        session.add(reg)
        await session.commit()
        reg_id = str(reg.id)

    token = make_token(seed_admin_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/admin/registration-requests/{reg_id}/status",
            json={"status": "approved", "notes": "All good"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"


@pytest.mark.asyncio
async def test_student_cannot_update_registration_status(student_user):
    """Student gets 403 when trying to update registration status."""
    async with TestSessionLocal() as session:
        reg = RegistrationRequest(
            id=uuid.uuid4(),
            request_id="REQ-2026-0002",
            full_name="Test Student 2",
            email="teststudent2@test.com",
            mobile="8888888888",
            date_of_birth=datetime(2000, 1, 1).date(),
            is_minor=False,
            selected_programmes=["guitar"],
            status="email_verified",
            submitted_at=datetime.utcnow(),
            review_deadline=datetime.utcnow() + timedelta(hours=72),
        )
        session.add(reg)
        await session.commit()
        reg_id = str(reg.id)

    token = make_token(student_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.patch(
            f"/api/v1/admin/registration-requests/{reg_id}/status",
            json={"status": "approved"},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_get_registration_detail(seed_admin_user):
    """Admin can GET /admin/registration-requests/:id."""
    async with TestSessionLocal() as session:
        reg = RegistrationRequest(
            id=uuid.uuid4(),
            request_id="REQ-2026-0003",
            full_name="Detail Test",
            email="detail@test.com",
            mobile="7777777777",
            date_of_birth=datetime(2005, 6, 15).date(),
            is_minor=False,
            selected_programmes=["piano", "music_theory"],
            status="pending_review",
            submitted_at=datetime.utcnow(),
            review_deadline=datetime.utcnow() + timedelta(hours=72),
        )
        session.add(reg)
        await session.commit()
        reg_id = str(reg.id)

    token = make_token(seed_admin_user)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/api/v1/admin/registration-requests/{reg_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Detail Test"
    assert data["email"] == "detail@test.com"
    assert data["status"] == "pending_review"
    assert data["selected_programmes"] == ["piano", "music_theory"]
    assert data["review_deadline"] is not None
