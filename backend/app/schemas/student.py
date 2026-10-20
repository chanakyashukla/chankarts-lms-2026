from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime, date
from uuid import UUID
import re


class GuardianBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    relationship: str = Field(..., min_length=1, max_length=50)
    phone: str = Field(..., min_length=10, max_length=20)
    email: Optional[str] = None
    address: Optional[str] = None
    is_primary: str = Field(default="N", pattern="^[YN]$")
    notes: Optional[str] = None


class GuardianCreate(GuardianBase):
    pass


class GuardianUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    relationship: Optional[str] = Field(None, min_length=1, max_length=50)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    email: Optional[str] = None
    address: Optional[str] = None
    is_primary: Optional[str] = Field(None, pattern="^[YN]$")
    notes: Optional[str] = None


class GuardianResponse(GuardianBase):
    id: UUID
    student_id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True


class InstrumentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=100)
    instrument_type: str = Field(..., pattern="^(instrument|discipline)$")
    description: Optional[str] = None


class InstrumentCreate(InstrumentBase):
    pass


class InstrumentResponse(InstrumentBase):
    id: UUID
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


class StudentInstrumentBase(BaseModel):
    instrument_id: UUID
    proficiency_level: Optional[str] = Field(None, pattern="^(beginner|intermediate|advanced)$")
    is_primary: str = Field(default="N", pattern="^[YN]$")
    notes: Optional[str] = None


class StudentInstrumentCreate(StudentInstrumentBase):
    pass


class StudentInstrumentResponse(StudentInstrumentBase):
    id: UUID
    student_id: UUID
    instrument: InstrumentResponse
    created_at: datetime
    
    class Config:
        from_attributes = True


class StudentBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    # optional: admin-provisioned students may enrol without a recorded date of birth
    date_of_birth: Optional[date] = None
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    address: Optional[str] = None
    skill_level: Optional[str] = Field(None, pattern="^(beginner|intermediate|advanced)$")
    
    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v is not None:
            cleaned = re.sub(r"[\s\-\(\)]", "", v)
            if not re.match(r"^\+?[\d]{10,15}$", cleaned):
                raise ValueError("Invalid phone number format")
        return v
    
    @field_validator("date_of_birth")
    @classmethod
    def validate_date_of_birth(cls, v):
        if v is not None and v > date.today():
            raise ValueError("Date of birth cannot be in the future")
        return v


class StudentCreate(StudentBase):
    user_id: UUID
    guardians: List[GuardianCreate] = []
    instruments: List[StudentInstrumentCreate] = []
    
    @model_validator(mode="after")
    def validate_guardians_for_minors(self):
        # no date of birth recorded -> cannot compute age; guardian policy is
        # applied by the admin workflow instead of blocking provisioning
        if self.date_of_birth is None:
            return self
        today = date.today()
        age = today.year - self.date_of_birth.year - (
            (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day)
        )
        if age < 18 and len(self.guardians) == 0:
            raise ValueError("Students under 18 must have at least one guardian")
        return self


class StudentUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=100)
    last_name: Optional[str] = Field(None, min_length=1, max_length=100)
    phone: Optional[str] = Field(None, min_length=10, max_length=20)
    address: Optional[str] = None
    skill_level: Optional[str] = Field(None, pattern="^(beginner|intermediate|advanced)$")
    status: Optional[str] = Field(None, pattern="^(active|inactive|suspended|graduated|transferred)$")
    profile_image_url: Optional[str] = None
    notes: Optional[str] = None


class StudentResponse(StudentBase):
    id: UUID
    cma_registration_id: str
    user_id: UUID
    status: str
    profile_image_url: Optional[str] = None
    profile_complete: bool
    guardians: List[GuardianResponse] = []
    student_instruments: List[StudentInstrumentResponse] = []
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class StudentProfileComplete(BaseModel):
    student_id: UUID
    cma_registration_id: str
    profile_complete: bool
    missing_fields: List[str]
    has_guardians: bool
    has_instruments: bool
    age: int
