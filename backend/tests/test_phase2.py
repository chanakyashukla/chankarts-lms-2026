import pytest
import pytest_asyncio
import asyncio
from datetime import date, datetime
from uuid import uuid4
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.database import Base, get_db
from app.models.user import User
from app.models.student import Student
from app.models.guardian import Guardian
from app.models.instrument import Instrument, StudentInstrument
from app.core.security import get_password_hash, create_access_token
from app.core.roles import UserRole

# Test database URL (use SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def admin_user():
    async with TestSessionLocal() as session:
        user = User(
            email="admin@test.com",
            username="admin",
            hashed_password=get_password_hash("password123"),
            role=UserRole.ADMIN
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def instructor_user():
    async with TestSessionLocal() as session:
        user = User(
            email="instructor@test.com",
            username="instructor",
            hashed_password=get_password_hash("password123"),
            role=UserRole.INSTRUCTOR
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def student_user():
    async with TestSessionLocal() as session:
        user = User(
            email="student@test.com",
            username="student",
            hashed_password=get_password_hash("password123"),
            role=UserRole.STUDENT
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def admin_token(admin_user):
    return create_access_token(
        data={"sub": str(admin_user.id), "role": admin_user.role.value}
    )


@pytest_asyncio.fixture
async def instructor_token(instructor_user):
    return create_access_token(
        data={"sub": str(instructor_user.id), "role": instructor_user.role.value}
    )


@pytest_asyncio.fixture
async def student_token(student_user):
    return create_access_token(
        data={"sub": str(student_user.id), "role": student_user.role.value}
    )


@pytest_asyncio.fixture
async def test_instrument():
    async with TestSessionLocal() as session:
        instrument = Instrument(
            name="piano",
            display_name="Piano",
            instrument_type="instrument",
            description="Acoustic or digital piano"
        )
        session.add(instrument)
        await session.commit()
        await session.refresh(instrument)
        return instrument


class TestStudentRegistration:
    @pytest.mark.asyncio
    async def test_create_student_as_admin(self, client, admin_token, admin_user, test_instrument):
        response = await client.post(
            "/api/v1/students/",
            json={
                "user_id": str(admin_user.id),
                "first_name": "Test",
                "last_name": "Student",
                "date_of_birth": "2000-01-01",
                "phone": "+1234567890",
                "instruments": [
                    {
                        "instrument_id": str(test_instrument.id),
                        "proficiency_level": "beginner"
                    }
                ],
                "guardians": []
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["first_name"] == "Test"
        assert data["last_name"] == "Student"
        assert data["cma_registration_id"].startswith("CMA-2026-")
        assert data["status"] == "active"
    
    @pytest.mark.asyncio
    async def test_cma_id_generation_sequential(self, client, admin_token, admin_user, test_instrument):
        # Create first student
        response1 = await client.post(
            "/api/v1/students/",
            json={
                "user_id": str(uuid4()),
                "first_name": "First",
                "last_name": "Student",
                "date_of_birth": "2000-01-01",
                "instruments": [{"instrument_id": str(test_instrument.id)}]
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response1.status_code == 200
        cma_id1 = response1.json()["cma_registration_id"]
        
        # Create second student
        response2 = await client.post(
            "/api/v1/students/",
            json={
                "user_id": str(uuid4()),
                "first_name": "Second",
                "last_name": "Student",
                "date_of_birth": "2001-01-01",
                "instruments": [{"instrument_id": str(test_instrument.id)}]
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response2.status_code == 200
        cma_id2 = response2.json()["cma_registration_id"]
        
        # Verify sequential numbering
        seq1 = int(cma_id1.split("-")[-1])
        seq2 = int(cma_id2.split("-")[-1])
        assert seq2 == seq1 + 1
    
    @pytest.mark.asyncio
    async def test_minor_requires_guardian(self, client, admin_token, test_instrument):
        # Student under 18 without guardian should fail
        response = await client.post(
            "/api/v1/students/",
            json={
                "user_id": str(uuid4()),
                "first_name": "Minor",
                "last_name": "Student",
                "date_of_birth": "2015-01-01",  # Under 18
                "instruments": [{"instrument_id": str(test_instrument.id)}],
                "guardians": []
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 422  # Validation error
    
    @pytest.mark.asyncio
    async def test_minor_with_guardian_success(self, client, admin_token, test_instrument):
        response = await client.post(
            "/api/v1/students/",
            json={
                "user_id": str(uuid4()),
                "first_name": "Minor",
                "last_name": "Student",
                "date_of_birth": "2015-01-01",
                "instruments": [{"instrument_id": str(test_instrument.id)}],
                "guardians": [
                    {
                        "first_name": "Parent",
                        "last_name": "Name",
                        "relationship": "parent",
                        "phone": "+1234567890"
                    }
                ]
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["guardians"]) == 1
        assert data["guardians"][0]["first_name"] == "Parent"
    
    @pytest.mark.asyncio
    async def test_duplicate_user_profile_rejected(self, client, admin_token, admin_user, test_instrument):
        # Create first student
        await client.post(
            "/api/v1/students/",
            json={
                "user_id": str(admin_user.id),
                "first_name": "First",
                "last_name": "Student",
                "date_of_birth": "2000-01-01",
                "instruments": [{"instrument_id": str(test_instrument.id)}]
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        # Try to create second student with same user
        response = await client.post(
            "/api/v1/students/",
            json={
                "user_id": str(admin_user.id),
                "first_name": "Second",
                "last_name": "Student",
                "date_of_birth": "2001-01-01",
                "instruments": [{"instrument_id": str(test_instrument.id)}]
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 400


class TestStudentProfile:
    @pytest.mark.asyncio
    async def test_get_own_profile(self, client, student_token, student_user):
        # Create student profile first
        async with TestSessionLocal() as session:
            student = Student(
                user_id=student_user.id,
                cma_registration_id="CMA-2026-0001",
                first_name="Test",
                last_name="Student",
                date_of_birth=date(2000, 1, 1),
                status="active"
            )
            session.add(student)
            await session.commit()
            await session.refresh(student)
            student_id = student.id
        
        response = await client.get(
            f"/api/v1/students/{student_id}",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert response.status_code == 200
        assert response.json()["first_name"] == "Test"
    
    @pytest.mark.asyncio
    async def test_cannot_view_other_student_profile(self, client, student_token, admin_user):
        # Create another student
        async with TestSessionLocal() as session:
            student = Student(
                user_id=admin_user.id,
                cma_registration_id="CMA-2026-0002",
                first_name="Other",
                last_name="Student",
                date_of_birth=date(2000, 1, 1),
                status="active"
            )
            session.add(student)
            await session.commit()
            await session.refresh(student)
            student_id = student.id
        
        response = await client.get(
            f"/api/v1/students/{student_id}",
            headers={"Authorization": f"Bearer {student_token}"}
        )
        assert response.status_code == 403


class TestInstruments:
    @pytest.mark.asyncio
    async def test_create_instrument(self, client, admin_token):
        response = await client.post(
            "/api/v1/instruments/",
            json={
                "name": "drums",
                "display_name": "Drums",
                "instrument_type": "instrument",
                "description": "Drum kit"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert response.json()["name"] == "drums"
    
    @pytest.mark.asyncio
    async def test_list_instruments(self, client, test_instrument):
        response = await client.get("/api/v1/instruments/")
        assert response.status_code == 200
        assert len(response.json()) > 0
    
    @pytest.mark.asyncio
    async def test_add_instrument_to_student(self, client, admin_token, admin_user, test_instrument):
        # Create student first
        async with TestSessionLocal() as session:
            student = Student(
                user_id=admin_user.id,
                cma_registration_id="CMA-2026-0003",
                first_name="Test",
                last_name="Student",
                date_of_birth=date(2000, 1, 1),
                status="active"
            )
            session.add(student)
            await session.commit()
            await session.refresh(student)
            student_id = student.id
        
        response = await client.post(
            f"/api/v1/students/{student_id}/instruments",
            json={
                "instrument_id": str(test_instrument.id),
                "proficiency_level": "intermediate",
                "is_primary": "Y"
            },
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert response.json()["proficiency_level"] == "intermediate"


class TestProfileCompleteness:
    @pytest.mark.asyncio
    async def test_incomplete_profile(self, client, admin_token, admin_user):
        # Create student without instruments
        async with TestSessionLocal() as session:
            student = Student(
                user_id=admin_user.id,
                cma_registration_id="CMA-2026-0004",
                first_name="Test",
                last_name="Student",
                date_of_birth=date(2000, 1, 1),
                status="active"
            )
            session.add(student)
            await session.commit()
            await session.refresh(student)
            student_id = student.id
        
        response = await client.get(
            f"/api/v1/students/{student_id}/profile",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["profile_complete"] == False
        assert "at least one instrument/discipline" in data["missing_fields"]
