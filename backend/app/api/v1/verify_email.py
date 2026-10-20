"""
Email verification endpoints for ChankArts Music Academy.
Handles verification token generation and email verification.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import hashlib
import secrets

from app.database import get_db
from app.models.registration_request import RegistrationRequest, RegistrationRequestStatus
from app.models.email_verification import EmailVerificationToken
from app.services.email import email_service
from app.config import get_settings

router = APIRouter()
settings = get_settings()


def hash_token(token: str) -> str:
    """Hash a token using SHA-256 for secure storage."""
    return hashlib.sha256(token.encode()).hexdigest()


class VerifyRequest(BaseModel):
    email: str = Field(..., max_length=255)


class VerifyConfirm(BaseModel):
    token: str = Field(..., min_length=1)


@router.post("/verify-email/request")
async def request_verification(
    data: VerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a verification email to the submitted email address."""
    
    # Find the registration request
    result = await db.execute(
        select(RegistrationRequest).where(
            RegistrationRequest.email == data.email.lower().strip()
        ).order_by(RegistrationRequest.submitted_at.desc())
    )
    registration = result.scalar_one_or_none()
    
    if not registration:
        # Don't reveal whether email exists
        return {"success": True, "message": "If an account exists, a verification email has been sent."}
    
    # Check if already verified
    if registration.status in [RegistrationRequestStatus.APPROVED]:
        return {"success": True, "message": "Email already verified."}
    
    # Invalidate any existing unused tokens for this registration
    existing_tokens = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.registration_request_id == registration.id,
            EmailVerificationToken.is_used == False,
        )
    )
    for token in existing_tokens.scalars().all():
        token.is_used = True
    
    # Generate new verification token
    raw_token = secrets.token_urlsafe(32)
    token_hash_val = hash_token(raw_token)
    
    verification_token = EmailVerificationToken(
        token_hash=token_hash_val,
        registration_request_id=registration.id,
        email=registration.email,
        is_used=False,
        expires_at=datetime.utcnow() + timedelta(hours=24),
    )
    
    db.add(verification_token)
    await db.flush()
    
    # Build verification URL
    base_url = settings.FRONTEND_URL
    verify_url = f"{base_url}/academy/verify-email?token={raw_token}"
    
    # Send verification email
    try:
        email_service.send_verification_email(
            to_email=registration.email,
            full_name=registration.full_name,
            verify_url=verify_url,
            expires_hours=24,
        )
    except Exception as e:
        # Don't fail the request if email fails
        pass
    
    return {"success": True, "message": "If an account exists, a verification email has been sent."}


@router.post("/verify-email/confirm")
async def confirm_verification(
    data: VerifyConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Verify the email using the token from the verification link."""
    
    # Hash the provided token
    token_hash_val = hash_token(data.token)
    
    # Find the token
    result = await db.execute(
        select(EmailVerificationToken).where(
            EmailVerificationToken.token_hash == token_hash_val
        )
    )
    verification = result.scalar_one_or_none()
    
    if not verification:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification link."
        )
    
    # Check if already used
    if verification.is_used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has already been used."
        )
    
    # Check expiry
    if datetime.utcnow() > verification.expires_at:
        verification.is_used = True
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link has expired. Please request a new one."
        )
    
    # Mark token as used
    verification.is_used = True
    verification.used_at = datetime.utcnow()
    
    # Update registration request status
    reg_result = await db.execute(
        select(RegistrationRequest).where(
            RegistrationRequest.id == verification.registration_request_id
        )
    )
    registration = reg_result.scalar_one_or_none()
    
    if registration:
        registration.status = RegistrationRequestStatus.PENDING
        registration.updated_at = datetime.utcnow()
    
    await db.flush()
    
    return {
        "success": True,
        "message": "Email verified successfully. Your registration is pending Academy approval.",
    }
