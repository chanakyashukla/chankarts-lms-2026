from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
from pydantic import BaseModel, EmailStr
from app.database import get_db
from app.models.user import User
from app.models.student import Student
from app.schemas.user import UserCreate, UserResponse, Token
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
)
from app.core.roles import UserRole
from app.core.ratelimit import client_key, enforce_rate_limit
from app.api.deps import get_current_user
from app.config import get_settings
from app.services.ids import next_sequence_value
from app.models.pin_reset import PinResetRequest, PinResetRequestStatus

router = APIRouter()
settings = get_settings()


class LoginRequest(BaseModel):
    # str (not EmailStr): students sign in with roll ID (CMA-001) and
    # admins with their username; email login still works.
    email: str
    password: str


class ChangePinRequest(BaseModel):
    current_pin: str
    new_pin: str


class PinResetRequestIn(BaseModel):
    """Forgot-PIN request from a student (admin-managed recovery only)."""
    username: str   # CMA Roll Number / Login ID
    contact: str    # registered phone or email the academy can reply to
    details: str = ""


@router.post("/register", response_model=UserResponse)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """Disabled: private academy LMS.

    Public self-registration is disabled — student accounts and credentials
    are provisioned by the administrator only (previous implementation is
    retained in git history).
    """
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Public registration is disabled. Student accounts are provisioned by the academy administrator.",
    )


@router.post("/login", response_model=Token)
async def login(
    request: Request,
    payload: LoginRequest | None = None,
    email: str | None = None,
    password: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a JSON body `{"email": ..., "password": ...}` (preferred) or the
    legacy query-parameter form. Email may also be a CMA Registration ID so
    the portal can sign in with either identifier — a password is always
    required; the CMA ID alone never grants access.
    """
    body_email = payload.email if payload else None
    body_password = payload.password if payload else None
    login_email = (body_email or email or "").strip()
    login_password = body_password or password or ""

    if not login_email or not login_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email and password are required",
        )

    enforce_rate_limit(
        "auth_login",
        client_key(request),
        settings.AUTH_RATE_LIMIT_ATTEMPTS,
        settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )

    # Match by email OR username (roll IDs like CMA-001 and logins like
    # chanakya.shukla are usernames; email remains supported).
    query = select(User).where(
        (User.email == login_email.lower()) | (User.username == login_email)
    )
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    # Allow sign-in with CMA Registration ID as the identifier
    if user is None and login_email.upper().startswith("CMA-"):
        cma_result = await db.execute(
            select(Student).where(Student.cma_registration_id.ilike(login_email))
        )
        student = cma_result.scalar_one_or_none()
        if student:
            result = await db.execute(select(User).where(User.id == student.user_id))
            user = result.scalar_one_or_none()

    if not user or not verify_password(login_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    # defence in depth: a suspended/archived student record also blocks sign-in,
    # even if the account flag was missed by an older workflow
    if user.role == UserRole.STUDENT:
        from app.models.student import Student as _Student
        st = (await db.execute(select(_Student).where(_Student.user_id == user.id))).scalar_one_or_none()
        if st is not None and st.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user"
            )

    access_token = create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    # Bundle the minimal profile the SPA needs for role-aware routing
    cma_id = None
    slug = None
    name = None
    if user.role == UserRole.STUDENT:
        student_result = await db.execute(select(Student).where(Student.user_id == user.id))
        student = student_result.scalar_one_or_none()
        if student:
            cma_id = student.cma_registration_id
            slug = student.portal_slug
            name = student.full_name
    elif user.role == UserRole.INSTRUCTOR:
        from app.models.instructor import Instructor
        instructor_result = await db.execute(select(Instructor).where(Instructor.user_id == user.id))
        instructor = instructor_result.scalar_one_or_none()
        if instructor:
            name = f"{instructor.first_name} {instructor.last_name}"
    elif user.role == UserRole.ADMIN:
        from app.models.admin import Admin
        admin_result = await db.execute(select(Admin).where(Admin.user_id == user.id))
        admin = admin_result.scalar_one_or_none()
        if admin:
            name = f"{admin.first_name} {admin.last_name}"

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role.value,
        "user_id": str(user.id),
        "name": name,
        "cma_registration_id": cma_id,
        "portal_slug": slug,
        "must_change_pin": bool(user.must_change_pin),
    }


@router.post("/change-pin")
async def change_pin(
    request: Request,
    payload: ChangePinRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Change the signed-in user's 4-digit PIN (required on first login).

    Stores only a secure hash; the new PIN must be exactly four digits.
    Rate-limited like login to resist guessing.
    """
    import re

    enforce_rate_limit(
        "auth_change_pin",
        client_key(request),
        settings.AUTH_RATE_LIMIT_ATTEMPTS,
        settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    )

    if not re.fullmatch(r"\d{4}", payload.new_pin):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New PIN must be exactly four digits",
        )

    if not verify_password(payload.current_pin, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current PIN is incorrect",
        )

    if payload.current_pin == payload.new_pin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New PIN must be different from the current PIN",
        )

    current_user.hashed_password = get_password_hash(payload.new_pin)
    current_user.must_change_pin = False
    db.add(current_user)
    await db.flush()

    return {"status": "ok", "must_change_pin": False}



@router.post("/pin-reset-request", status_code=status.HTTP_201_CREATED)
async def request_pin_reset(
    request: Request,
    payload: PinResetRequestIn,
    db: AsyncSession = Depends(get_db),
):
    """Public Forgot-PIN request.

    Academy policy: recovery is admin-managed (temporary PIN issued in person),
    never an emailed reset link. The response is deliberately identical whether
    or not the submitted login id exists, so this endpoint cannot be used to
    enumerate accounts.
    """
    enforce_rate_limit(
        "pin_reset_request",
        client_key(request),
        settings.REGISTRATION_RATE_LIMIT_ATTEMPTS,
        settings.REGISTRATION_RATE_LIMIT_WINDOW_SECONDS,
    )

    username = payload.username.strip()
    contact = payload.contact.strip()
    details = (payload.details or "").strip()

    if not username or len(username) > 100:
        raise HTTPException(status_code=400, detail="Please provide your Roll No. / Login ID")
    if not contact or len(contact) > 255:
        raise HTTPException(status_code=400, detail="Please provide a contact the academy can reply to")

    generic = {
        "message": "Your request has been received. The academy will contact you "
                   "using your registered contact details.",
        "status": "received",
    }

    # Only record the request when the account actually exists — but the HTTP
    # response stays identical either way (no account-existence disclosure).
    user_result = await db.execute(select(User).where(User.username == username))
    user = user_result.scalar_one_or_none()
    if user is None:
        # also try email as identifier (legacy accounts), still generic response
        user_result = await db.execute(select(User).where(User.email == username.lower()))
        user = user_result.scalar_one_or_none()

    if user is not None:
        # collapse repeated requests: one open request per account
        existing = await db.execute(
            select(PinResetRequest).where(
                PinResetRequest.resolved_user_id == user.id,
                PinResetRequest.status == PinResetRequestStatus.PENDING,
            )
        )
        if existing.scalar_one_or_none():
            return generic
        year = datetime.utcnow().year
        seq = await next_sequence_value(db, f"pinreq_seq_{year}")
        db.add(PinResetRequest(
            request_id=f"PINREQ-{year}-{seq:04d}",
            username_submitted=username,
            contact=contact,
            details=details or None,
            status=PinResetRequestStatus.PENDING,
            resolved_user_id=user.id,
        ))
        await db.flush()

    return generic


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
