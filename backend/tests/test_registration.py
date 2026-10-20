"""
Tests for the public registration endpoint.
Tests both adult and minor registrations, validation, duplicate protection, 72-hour deadline, email verification, and Web3Forms email delivery.
"""
import pytest
import pytest_asyncio
import re
import hashlib
from datetime import datetime, timedelta
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from unittest.mock import patch, MagicMock

# Test database URL (use SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_registration.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# Import after engine setup to avoid circular imports
from app.main import app
from app.database import get_db, Base
from app.models.registration_request import RegistrationRequest
from app.models.email_verification import EmailVerificationToken
from app.services.email import email_service


def hash_token(token: str) -> str:
    """Hash a token using SHA-256 for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


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


@pytest.fixture
def adult_payload():
    return {
        "fullName": "Test Student",
        "email": "test.student@example.com",
        "mobile": "+919876543210",
        "password": "securepassword123",
        "dateOfBirth": "2000-01-15",
        "isMinor": False,
        "address": "123 Test Street, Mumbai",
        "selectedProgrammes": [
            {"id": "piano", "name": "Piano"},
            {"id": "guitar", "name": "Acoustic Guitar"}
        ]
    }


@pytest.fixture
def minor_payload():
    return {
        "fullName": "Young Student",
        "email": "young.student@example.com",
        "mobile": "+919876543211",
        "password": "securepassword123",
        "dateOfBirth": "2012-05-20",
        "isMinor": True,
        "address": "456 Test Avenue, Delhi",
        "guardianName": "Parent Name",
        "guardianRelationship": "Mother",
        "guardianEmail": "parent@example.com",
        "guardianMobile": "+919876543212",
        "selectedProgrammes": [
            {"id": "keyboard", "name": "Electronic Keyboard"},
            {"id": "vocals", "name": "Western Vocals"}
        ]
    }


# ========================================
# Basic Registration Tests
# ========================================
@pytest.mark.asyncio
async def test_adult_registration_success(client, adult_payload):
    """Test successful adult registration."""
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["request_id"].startswith("REQ-")
    assert data["status"] == "pending_review"
    assert "submitted_at" in data
    assert "review_deadline" in data


@pytest.mark.asyncio
async def test_minor_registration_success(client, minor_payload):
    """Test successful minor registration with guardian information."""
    response = await client.post("/api/v1/registration-requests", json=minor_payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["request_id"].startswith("REQ-")


# ========================================
# Validation Tests
# ========================================
@pytest.mark.asyncio
async def test_minor_without_guardian_rejected(client):
    """Test that minor registration without guardian info is rejected."""
    payload = {
        "fullName": "Young Student",
        "email": "young.student@example.com",
        "mobile": "+919876543211",
        "password": "securepassword123",
        "dateOfBirth": "2012-05-20",
        "isMinor": True,
        "selectedProgrammes": [{"id": "piano", "name": "Piano"}]
    }
    
    response = await client.post("/api/v1/registration-requests", json=payload)
    
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_invalid_email_rejected(client):
    """Test that invalid email is rejected."""
    payload = {
        "fullName": "Test Student",
        "email": "invalid-email",
        "mobile": "+919876543210",
        "password": "securepassword123",
        "dateOfBirth": "2000-01-15",
        "isMinor": False,
        "selectedProgrammes": [{"id": "piano", "name": "Piano"}]
    }
    
    response = await client.post("/api/v1/registration-requests", json=payload)
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_mobile_rejected(client):
    """Test that invalid mobile number is rejected."""
    payload = {
        "fullName": "Test Student",
        "email": "test@example.com",
        "mobile": "123",
        "password": "securepassword123",
        "dateOfBirth": "2000-01-15",
        "isMinor": False,
        "selectedProgrammes": [{"id": "piano", "name": "Piano"}]
    }
    
    response = await client.post("/api/v1/registration-requests", json=payload)
    
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_password_is_not_collected(client):
    """Applications are enquiries only — no password is created or stored."""
    payload = {
        "fullName": "Test Student",
        "email": "test@example.com",
        "mobile": "+919876543210",
        "dateOfBirth": "2000-01-15",
        "isMinor": False,
        "selectedProgrammes": [{"id": "piano", "name": "Piano"}]
    }

    # submission works with NO password field at all
    response = await client.post("/api/v1/registration-requests", json=payload)
    assert response.status_code == 201

    # a legacy client that still sends a password must not cause any
    # credential to be stored
    payload2 = dict(payload, email="test2@example.com", password="whatever123")
    response2 = await client.post("/api/v1/registration-requests", json=payload2)
    assert response2.status_code == 201
    async with TestSessionLocal() as session:
        rows = (await session.execute(select(RegistrationRequest))).scalars().all()
        for r in rows:
            assert not hasattr(r, "password_hash") or getattr(r, "password_hash", None) is None


@pytest.mark.asyncio
async def test_no_programmes_rejected(client):
    """Test that registration without programmes is rejected."""
    payload = {
        "fullName": "Test Student",
        "email": "test@example.com",
        "mobile": "+919876543210",
        "password": "securepassword123",
        "dateOfBirth": "2000-01-15",
        "isMinor": False,
        "selectedProgrammes": []
    }
    
    response = await client.post("/api/v1/registration-requests", json=payload)
    
    assert response.status_code == 422


# ========================================
# Duplicate Submission Tests
# ========================================
@pytest.mark.asyncio
async def test_duplicate_submission_prevention(client, adult_payload):
    """Test that duplicate submissions within 1 hour are prevented."""
    # First submission
    response1 = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response1.status_code == 201
    
    # Second submission with same email
    response2 = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response2.status_code == 409


# ========================================
# 72-Hour Deadline Tests
# ========================================
@pytest.mark.asyncio
async def test_72_hour_deadline(client, adult_payload):
    """Test that review_deadline is 72 hours after submission."""
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    data = response.json()
    
    submitted_at = datetime.fromisoformat(data["submitted_at"].replace("Z", "+00:00"))
    review_deadline = datetime.fromisoformat(data["review_deadline"].replace("Z", "+00:00"))
    
    # Allow some tolerance for test execution time
    expected_deadline = submitted_at + timedelta(hours=72)
    assert abs((review_deadline - expected_deadline).total_seconds()) < 60


# ========================================
# Password Security Tests
# ========================================
@pytest.mark.asyncio
async def test_password_not_returned(client, adult_payload):
    """Test that password is never returned in response."""
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    data = response.json()

    assert "password" not in data
    assert "password_hash" not in data
    # no account credentials are issued at application time
    assert "temp_pin" not in data and "access_token" not in data


@pytest.mark.asyncio
async def test_password_not_in_database(client, adult_payload):
    """Test that password is not stored in database."""
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    
    # Verify in database
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(RegistrationRequest).where(
                RegistrationRequest.email == adult_payload["email"]
            )
        )
        registration = result.scalar_one_or_none()

        assert registration is not None
        # the application carries no credential data whatsoever
        assert not hasattr(registration, "password_hash")


# ========================================
# Email Content Tests
# ========================================
@pytest.mark.asyncio
async def test_email_not_in_email_body(client, adult_payload):
    """Test that password is not included in email content."""
    email_service.clear_test_emails()
    
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    
    # Check captured emails
    test_emails = email_service.get_test_emails()
    assert len(test_emails) == 2  # Admin notification + student confirmation
    
    for email_record in test_emails:
        assert adult_payload["password"] not in email_record["text_body"]
        assert adult_payload["password"] not in email_record["html_body"]


@pytest.mark.asyncio
async def test_email_contains_all_non_sensitive_fields(client, adult_payload):
    """Test that email contains all non-sensitive registration fields."""
    email_service.clear_test_emails()
    
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    data = response.json()
    
    # Check admin notification email
    test_emails = email_service.get_test_emails()
    assert len(test_emails) >= 1
    
    admin_email = test_emails[0]
    
    # Verify all non-sensitive fields are in the email
    assert data["request_id"] in admin_email["text_body"]
    assert adult_payload["fullName"] in admin_email["text_body"]
    assert adult_payload["email"] in admin_email["text_body"]
    assert adult_payload["mobile"] in admin_email["text_body"]
    assert adult_payload["dateOfBirth"] in admin_email["text_body"]
    assert "Adult (18+)" in admin_email["text_body"]
    
    # Verify programmes are included
    for programme in adult_payload["selectedProgrammes"]:
        assert programme["name"] in admin_email["text_body"]


@pytest.mark.asyncio
async def test_minor_email_contains_guardian_info(client, minor_payload):
    """Test that minor registration email contains guardian information."""
    email_service.clear_test_emails()
    
    response = await client.post("/api/v1/registration-requests", json=minor_payload)
    
    assert response.status_code == 201
    
    # Check admin notification email
    test_emails = email_service.get_test_emails()
    assert len(test_emails) >= 1
    
    admin_email = test_emails[0]
    
    # Verify guardian information is included
    assert minor_payload["guardianName"] in admin_email["text_body"]
    assert minor_payload["guardianRelationship"] in admin_email["text_body"]
    assert minor_payload["guardianMobile"] in admin_email["text_body"]
    assert "Minor (Under 18)" in admin_email["text_body"]


# ========================================
# Programme Tests
# ========================================
@pytest.mark.asyncio
async def test_multiple_programmes(client):
    """Test registration with multiple programmes."""
    payload = {
        "fullName": "Multi Programme Student",
        "email": "multi@example.com",
        "mobile": "+919876543210",
        "password": "securepassword123",
        "dateOfBirth": "2000-01-15",
        "isMinor": False,
        "selectedProgrammes": [
            {"id": "piano", "name": "Piano"},
            {"id": "guitar", "name": "Acoustic Guitar"},
            {"id": "vocals", "name": "Western Vocals"},
            {"id": "theory", "name": "Music Theory"}
        ]
    }
    
    response = await client.post("/api/v1/registration-requests", json=payload)
    
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_programme_persistence(client, adult_payload):
    """Test that selected programmes are persisted correctly."""
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    
    # Verify in database
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(RegistrationRequest).where(
                RegistrationRequest.email == adult_payload["email"]
            )
        )
        registration = result.scalar_one_or_none()
        
        assert registration is not None
        assert len(registration.selected_programmes) == 2
        assert registration.selected_programmes[0]["id"] == "piano"
        assert registration.selected_programmes[1]["id"] == "guitar"


# ========================================
# Request ID Tests
# ========================================
@pytest.mark.asyncio
async def test_request_id_format(client, adult_payload):
    """Test that request_id follows REQ-YYYY-#### format."""
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    data = response.json()
    
    pattern = r"^REQ-\d{4}-[A-F0-9]{4}$"
    assert re.match(pattern, data["request_id"])


# ========================================
# Status Persistence Tests
# ========================================
@pytest.mark.asyncio
async def test_status_persistence(client, adult_payload):
    """Test that initial status is pending_review."""
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    
    # Verify in database
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(RegistrationRequest).where(
                RegistrationRequest.email == adult_payload["email"]
            )
        )
        registration = result.scalar_one_or_none()
        
        assert registration is not None
        assert registration.status == "pending_review"


# ========================================
# Web3Forms Integration Tests
# ========================================
@pytest.mark.asyncio
async def test_web3forms_payload_structure(client, adult_payload):
    """Test that Web3Forms payload is correctly generated."""
    email_service.clear_test_emails()
    
    # Temporarily disable test mode to test payload structure
    original_test_mode = email_service.test_mode
    original_access_key = email_service.web3forms_access_key
    email_service.test_mode = False
    email_service.web3forms_access_key = "test-access-key"
    
    try:
        with patch('app.services.email.httpx.Client') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"success": True}
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            response = await client.post("/api/v1/registration-requests", json=adult_payload)
            
            assert response.status_code == 201
            
            # Verify Web3Forms was called (2 times: admin + student confirmation)
            assert mock_client.return_value.__enter__.return_value.post.call_count == 2
            
            # Check admin notification payload (first call)
            admin_call_args = mock_client.return_value.__enter__.return_value.post.call_args_list[0]
            assert admin_call_args[0][0] == "https://api.web3forms.com/submit"
            admin_payload = admin_call_args[1]["json"]
            assert "access_key" in admin_payload
            assert "to" in admin_payload
            assert "subject" in admin_payload
            assert "html" in admin_payload
            assert "text" in admin_payload
            assert admin_payload["to"] == "chankarts.official@gmail.com"
            assert adult_payload["fullName"] in admin_payload["subject"]
            
            # Check student confirmation payload (second call)
            student_call_args = mock_client.return_value.__enter__.return_value.post.call_args_list[1]
            student_payload = student_call_args[1]["json"]
            assert student_payload["to"] == adult_payload["email"]
    finally:
        email_service.test_mode = original_test_mode
        email_service.web3forms_access_key = original_access_key


@pytest.mark.asyncio
async def test_web3forms_test_mode_captures_email(client, adult_payload):
    """Test that test mode captures emails without sending."""
    email_service.clear_test_emails()
    
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    
    # Verify email was captured in test mode
    test_emails = email_service.get_test_emails()
    assert len(test_emails) == 2  # Admin + student confirmation
    
    # Verify admin email content
    admin_email = test_emails[0]
    assert admin_email["to"] == "chankarts.official@gmail.com"
    assert "New ChankArts Music Academy Registration" in admin_email["subject"]
    assert adult_payload["fullName"] in admin_email["subject"]


@pytest.mark.asyncio
async def test_web3forms_failure_does_not_affect_registration(client, adult_payload):
    """Test that Web3Forms failure does not delete/rollback registration."""
    email_service.clear_test_emails()
    
    # Temporarily disable test mode to simulate failure
    original_test_mode = email_service.test_mode
    original_access_key = email_service.web3forms_access_key
    email_service.test_mode = False
    email_service.web3forms_access_key = "test-access-key"
    
    try:
        with patch('app.services.email.httpx.Client') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"success": False, "message": "API key invalid"}
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            response = await client.post("/api/v1/registration-requests", json=adult_payload)
            
            # Registration should still succeed even if email fails
            assert response.status_code == 201
            data = response.json()
            assert data["success"] is True
            
            # Verify registration was saved in database
            async with TestSessionLocal() as session:
                result = await session.execute(
                    select(RegistrationRequest).where(
                        RegistrationRequest.email == adult_payload["email"]
                    )
                )
                registration = result.scalar_one_or_none()
                assert registration is not None
    finally:
        email_service.test_mode = original_test_mode
        email_service.web3forms_access_key = original_access_key


@pytest.mark.asyncio
async def test_web3forms_no_password_in_payload(client, adult_payload):
    """Test that password is never included in Web3Forms payload."""
    email_service.clear_test_emails()
    
    # Temporarily disable test mode to test payload
    original_test_mode = email_service.test_mode
    original_access_key = email_service.web3forms_access_key
    email_service.test_mode = False
    email_service.web3forms_access_key = "test-access-key"
    
    try:
        with patch('app.services.email.httpx.Client') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"success": True}
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            response = await client.post("/api/v1/registration-requests", json=adult_payload)
            
            assert response.status_code == 201
            
            # Verify password is not in Web3Forms payload
            call_args = mock_client.return_value.__enter__.return_value.post.call_args
            payload = call_args[1]["json"]
            
            assert adult_payload["password"] not in str(payload)
            assert "password" not in payload.get("html", "").lower()
    finally:
        email_service.test_mode = original_test_mode
        email_service.web3forms_access_key = original_access_key


@pytest.mark.asyncio
async def test_web3forms_access_key_not_exposed(client, adult_payload):
    """Test that Web3Forms access key is not exposed in response."""
    email_service.clear_test_emails()
    
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    
    assert response.status_code == 201
    data = response.json()
    
    # Verify access key is not in response
    assert "access_key" not in data
    assert "WEB3FORMS" not in str(data)


# ========================================
# Database Persistence Tests (Email Failure)
# ========================================
@pytest.mark.asyncio
async def test_registration_persists_when_email_fails(client, adult_payload):
    """Test that registration persists in database even when email delivery fails."""
    email_service.clear_test_emails()
    
    # Temporarily disable test mode to simulate failure
    original_test_mode = email_service.test_mode
    original_access_key = email_service.web3forms_access_key
    email_service.test_mode = False
    email_service.web3forms_access_key = "test-access-key"
    
    try:
        with patch('app.services.email.httpx.Client') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {"success": False, "message": "Service unavailable"}
            mock_response.raise_for_status = MagicMock()
            mock_client.return_value.__enter__.return_value.post.return_value = mock_response
            
            response = await client.post("/api/v1/registration-requests", json=adult_payload)
            
            # Registration should still succeed
            assert response.status_code == 201
            
            # Verify registration was saved in database
            async with TestSessionLocal() as session:
                result = await session.execute(
                    select(RegistrationRequest).where(
                        RegistrationRequest.email == adult_payload["email"]
                    )
                )
                registration = result.scalar_one_or_none()
                
                assert registration is not None
                assert registration.request_id.startswith("REQ-")
                assert registration.status == "pending_review"
                assert registration.full_name == adult_payload["fullName"]
    finally:
        email_service.test_mode = original_test_mode
        email_service.web3forms_access_key = original_access_key


# ========================================
# Email Verification Tests
# ========================================
@pytest.mark.asyncio
async def test_verification_token_creation(client, adult_payload):
    """Test that verification token is created when requested."""
    # First register
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response.status_code == 201
    
    # Request verification
    response = await client.post("/api/v1/verify-email/request", json={"email": adult_payload["email"]})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    
    # Verify token was created in database
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.email == adult_payload["email"]
            )
        )
        token = result.scalar_one_or_none()
        assert token is not None
        assert token.is_used is False
        assert token.expires_at > datetime.utcnow()


@pytest.mark.asyncio
async def test_verification_token_expiry(client, adult_payload):
    """Test that expired verification tokens are rejected."""
    # First register
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response.status_code == 201
    
    # Create an expired token manually
    raw_token = "expired-test-token"
    token_hash_val = hash_token(raw_token)
    
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(RegistrationRequest).where(
                RegistrationRequest.email == adult_payload["email"]
            )
        )
        registration = result.scalar_one_or_none()
        
        expired_token = EmailVerificationToken(
            token_hash=token_hash_val,
            registration_request_id=registration.id,
            email=adult_payload["email"],
            is_used=False,
            expires_at=datetime.utcnow() - timedelta(hours=1),  # Expired
        )
        session.add(expired_token)
        await session.commit()
    
    # Try to verify with expired token
    response = await client.post("/api/v1/verify-email/confirm", json={"token": raw_token})
    assert response.status_code == 400
    data = response.json()
    assert "expired" in data["detail"].lower()


@pytest.mark.asyncio
async def test_successful_email_verification(client, adult_payload):
    """Test successful email verification flow."""
    # First register
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response.status_code == 201
    
    # Request verification
    response = await client.post("/api/v1/verify-email/request", json={"email": adult_payload["email"]})
    assert response.status_code == 200
    
    # Get the token from database
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(EmailVerificationToken).where(
                EmailVerificationToken.email == adult_payload["email"]
            )
        )
        token = result.scalar_one_or_none()
        assert token is not None
    
    # Verify the token (we need to get the raw token, but we only have the hash)
    # Since we can't reverse the hash, we'll test with a known token
    raw_token = "test-verification-token"
    token_hash_val = hash_token(raw_token)
    
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(RegistrationRequest).where(
                RegistrationRequest.email == adult_payload["email"]
            )
        )
        registration = result.scalar_one_or_none()
        
        # Create a valid token
        valid_token = EmailVerificationToken(
            token_hash=token_hash_val,
            registration_request_id=registration.id,
            email=adult_payload["email"],
            is_used=False,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )
        session.add(valid_token)
        await session.commit()
    
    # Verify the token
    response = await client.post("/api/v1/verify-email/confirm", json={"token": raw_token})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "verified" in data["message"].lower()


@pytest.mark.asyncio
async def test_invalid_verification_token(client):
    """Test that invalid verification tokens are rejected."""
    response = await client.post("/api/v1/verify-email/confirm", json={"token": "invalid-token-12345"})
    assert response.status_code == 400
    data = response.json()
    assert "invalid" in data["detail"].lower()


@pytest.mark.asyncio
async def test_used_verification_token_rejected(client, adult_payload):
    """Test that already used verification tokens are rejected."""
    # First register
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response.status_code == 201
    
    # Create a used token
    raw_token = "used-test-token"
    token_hash_val = hash_token(raw_token)
    
    async with TestSessionLocal() as session:
        result = await session.execute(
            select(RegistrationRequest).where(
                RegistrationRequest.email == adult_payload["email"]
            )
        )
        registration = result.scalar_one_or_none()
        
        used_token = EmailVerificationToken(
            token_hash=token_hash_val,
            registration_request_id=registration.id,
            email=adult_payload["email"],
            is_used=True,  # Already used
            expires_at=datetime.utcnow() + timedelta(hours=24),
            used_at=datetime.utcnow(),
        )
        session.add(used_token)
        await session.commit()
    
    # Try to verify with used token
    response = await client.post("/api/v1/verify-email/confirm", json={"token": raw_token})
    assert response.status_code == 400
    data = response.json()
    assert "already been used" in data["detail"].lower()


@pytest.mark.asyncio
async def test_verification_email_sent(client, adult_payload):
    """Test that verification email is sent when requested."""
    email_service.clear_test_emails()
    
    # First register
    response = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response.status_code == 201
    
    # Request verification
    response = await client.post("/api/v1/verify-email/request", json={"email": adult_payload["email"]})
    assert response.status_code == 200
    
    # Check that verification email was captured
    test_emails = email_service.get_test_emails()
    verification_emails = [e for e in test_emails if "Verify" in e["subject"]]
    assert len(verification_emails) >= 1
    
    # Verify email content
    verification_email = verification_emails[0]
    assert adult_payload["fullName"] in verification_email["text_body"]
    assert "verify" in verification_email["text_body"].lower()


@pytest.mark.asyncio
async def test_duplicate_submission_from_repeated_clicks(client, adult_payload):
    """Test that rapid duplicate submissions are prevented."""
    # First submission
    response1 = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response1.status_code == 201
    
    # Second submission (simulating rapid double-click)
    response2 = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response2.status_code == 409  # Conflict - duplicate
    
    # Third submission (should also be blocked)
    response3 = await client.post("/api/v1/registration-requests", json=adult_payload)
    assert response3.status_code == 409


@pytest.mark.asyncio
async def test_verification_request_nonexistent_email(client):
    """Test that verification request for nonexistent email doesn't reveal existence."""
    response = await client.post("/api/v1/verify-email/request", json={"email": "nonexistent@example.com"})
    assert response.status_code == 200  # Should return success to prevent email enumeration
    data = response.json()
    assert data["success"] is True
