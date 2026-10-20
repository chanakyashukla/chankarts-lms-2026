"""
Public registration endpoint for ChankArts Music Academy.
This is the transmitter that receives registration form submissions.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, date
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional
import re

from app.database import get_db
from app.models.registration_request import RegistrationRequest, RegistrationRequestStatus
from app.core.ratelimit import client_key, enforce_rate_limit
from app.services.email import email_service
from app.services.ids import generate_request_id as _generate_request_id
from app.services.audit import record_audit
from app.config import get_settings

router = APIRouter()
settings = get_settings()


# ========================================
# Request ID Generator
# ========================================
async def generate_request_id(db) -> str:
    """Generate a unique, concurrency-safe request ID: REQ-YYYY-####"""
    return await _generate_request_id(db)


# ========================================
# Pydantic Schema
# ========================================
class ProgrammeItem(BaseModel):
    id: str
    name: str


class RegistrationSubmit(BaseModel):
    # Account
    fullName: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., max_length=255)
    mobile: str = Field(..., max_length=20)
    # no password is collected: applications are enquiries only — the admin
    # provisions the account and issues a temporary PIN explicitly
    
    # Student Details
    dateOfBirth: str  # YYYY-MM-DD
    isMinor: bool = False
    address: Optional[str] = None
    
    # Guardian (for minors)
    guardianName: Optional[str] = None
    guardianRelationship: Optional[str] = None
    guardianEmail: Optional[str] = None
    guardianMobile: Optional[str] = None
    
    # Programmes
    selectedProgrammes: List[ProgrammeItem] = Field(..., min_length=1)
    
    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", v):
            raise ValueError("Invalid email address")
        return v.lower().strip()
    
    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v):
        cleaned = re.sub(r"[\s\-\(\)]", "", v)
        if not re.match(r"^\+?[\d]{10,15}$", cleaned):
            raise ValueError("Invalid mobile number")
        return v.strip()
    
    @model_validator(mode="after")
    def validate_guardians_for_minors(self):
        if self.isMinor:
            if not self.guardianName:
                raise ValueError("Guardian name is required for minors")
            if not self.guardianMobile:
                raise ValueError("Guardian mobile is required for minors")
            if not self.guardianRelationship:
                raise ValueError("Guardian relationship is required for minors")
        return self


# ========================================
# Public Registration Endpoint
# ========================================
@router.post("/registration-requests", status_code=status.HTTP_201_CREATED)
async def submit_registration(
    data: RegistrationSubmit,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Public endpoint for student registration submissions.
    Creates a Registration Request and sends notification emails.
    """
    enforce_rate_limit(
        "registration_submit",
        client_key(request),
        settings.REGISTRATION_RATE_LIMIT_ATTEMPTS,
        settings.REGISTRATION_RATE_LIMIT_WINDOW_SECONDS,
    )

    # Check for duplicate email submissions (within last hour)
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    existing = await db.execute(
        select(RegistrationRequest).where(
            RegistrationRequest.email == data.email,
            RegistrationRequest.submitted_at > one_hour_ago
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A registration with this email was recently submitted. Please wait before submitting again."
        )
    
    # Parse date of birth
    try:
        dob = date.fromisoformat(data.dateOfBirth)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD."
        )
    
    # Generate request ID (sequential, concurrency-safe)
    request_id = await generate_request_id(db)
    
    # Calculate review deadline (72 hours from now)
    submitted_at = datetime.utcnow()
    review_deadline = submitted_at + timedelta(hours=72)
    
    # Create registration request
    registration = RegistrationRequest(
        request_id=request_id,
        status=RegistrationRequestStatus.PENDING,
        full_name=data.fullName.strip(),
        email=data.email,
        mobile=data.mobile.strip(),
        date_of_birth=dob,
        is_minor=data.isMinor,
        address=data.address.strip() if data.address else None,
        guardian_name=data.guardianName.strip() if data.guardianName else None,
        guardian_relationship=data.guardianRelationship if data.guardianRelationship else None,
        guardian_email=data.guardianEmail.strip() if data.guardianEmail else None,
        guardian_mobile=data.guardianMobile.strip() if data.guardianMobile else None,
        selected_programmes=[p.model_dump() for p in data.selectedProgrammes],
        submitted_at=submitted_at,
        review_deadline=review_deadline,
    )
    
    db.add(registration)
    await db.flush()
    
    # Send admin notification email
    programmes_list = [{"id": p.id, "name": p.name} for p in data.selectedProgrammes]
    
    try:
        email_service.send_registration_admin_notification(
            request_id=request_id,
            full_name=data.fullName,
            email=data.email,
            mobile=data.mobile,
            date_of_birth=data.dateOfBirth,
            is_minor=data.isMinor,
            address=data.address or "",
            guardian_name=data.guardianName or "",
            guardian_relationship=data.guardianRelationship or "",
            guardian_email=data.guardianEmail or "",
            guardian_mobile=data.guardianMobile or "",
            selected_programmes=programmes_list,
            submitted_at=submitted_at.strftime("%d %B %Y, %I:%M %p UTC"),
            review_deadline=review_deadline.strftime("%d %B %Y, %I:%M %p UTC"),
        )
    except Exception as e:
        # Don't fail the registration if email fails
        pass
    
    # Send student confirmation email
    try:
        email_service.send_student_confirmation(
            to_email=data.email,
            full_name=data.fullName,
            request_id=request_id,
            submitted_at=submitted_at.strftime("%d %B %Y, %I:%M %p UTC"),
        )
    except Exception as e:
        # Don't fail the registration if email fails
        pass

    await record_audit(
        db,
        action="registration.submitted",
        entity_type="registration_request",
        entity_id=request_id,
        summary=f"Registration submitted by {data.fullName}",
        after_data={"request_id": request_id, "email": data.email, "programmes": [p.id for p in data.selectedProgrammes]},
        ip_address=client_key(request),
    )

    return {
        "success": True,
        "request_id": request_id,
        "submitted_at": submitted_at.isoformat(),
        "review_deadline": review_deadline.isoformat(),
        "status": "pending_review",
        "message": "Registration submitted successfully. We will review your application within 72 hours.",
    }


class StatusCheckRequest(BaseModel):
    requestId: str = Field(..., max_length=20)
    email: str = Field(..., max_length=255)


# Friendly status labels — never expose applicant details in this response
_STATUS_LABELS = {
    RegistrationRequestStatus.PENDING: "Pending review",
    RegistrationRequestStatus.APPROVED: "Approved",
    RegistrationRequestStatus.REJECTED: "Closed",
    RegistrationRequestStatus.NEEDS_INFO: "Additional information requested",
}


@router.post("/registration-requests/status")
async def check_registration_status(
    data: StatusCheckRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Secure application-status lookup. Requires the application reference AND
    the registered email; response contains only a status label and timestamps.
    """
    enforce_rate_limit(
        "registration_status",
        client_key(request),
        settings.REGISTRATION_RATE_LIMIT_ATTEMPTS,
        settings.REGISTRATION_RATE_LIMIT_WINDOW_SECONDS,
    )

    result = await db.execute(
        select(RegistrationRequest).where(
            RegistrationRequest.request_id == data.requestId.strip().upper(),
            RegistrationRequest.email == data.email.lower().strip(),
        )
    )
    registration = result.scalar_one_or_none()

    # Uniform response shape — no existence oracle
    if not registration:
        return {
            "success": False,
            "message": "No application found for that reference and email combination.",
        }

    return {
        "success": True,
        "request_id": registration.request_id,
        "status": registration.status,
        "status_label": _STATUS_LABELS.get(registration.status, registration.status),
        "submitted_at": registration.submitted_at.isoformat() if registration.submitted_at else None,
        "review_deadline": registration.review_deadline.isoformat() if registration.review_deadline else None,
        "reviewed_at": registration.reviewed_at.isoformat() if registration.reviewed_at else None,
        "student_id": str(registration.student_id) if registration.student_id else None,
    }
