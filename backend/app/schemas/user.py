from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID
from app.core.roles import UserRole


class UserBase(BaseModel):
    email: Optional[EmailStr] = None
    username: str
    role: UserRole = UserRole.STUDENT


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: UUID
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Optional[str] = None
    user_id: Optional[str] = None
    name: Optional[str] = None
    cma_registration_id: Optional[str] = None
    portal_slug: Optional[str] = None
    must_change_pin: bool = False


class TokenData(BaseModel):
    user_id: Optional[str] = None
    role: Optional[UserRole] = None
