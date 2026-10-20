from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID
from datetime import date
from app.database import get_db
from app.models.user import User
from app.models.student import Student
from app.models.guardian import Guardian
from app.models.instrument import Instrument, StudentInstrument
from app.schemas.student import (
    StudentCreate,
    StudentUpdate,
    StudentResponse,
    StudentProfileComplete,
    GuardianCreate,
    GuardianResponse,
    InstrumentCreate,
    InstrumentResponse,
    StudentInstrumentCreate,
    StudentInstrumentResponse,
)
from app.core.roles import UserRole
from app.api.deps import get_current_user, require_role
from app.services.access import require_student_access, get_linked_student_ids
from app.models.enrollment import Enrollment
from app.services.cma_id import CMAIdService
from app.services.profile import ProfileService

router = APIRouter()


def _student_with_relations():
    return (
        selectinload(Student.guardians),
        selectinload(Student.student_instruments).selectinload(StudentInstrument.instrument),
    )


def _guardian_kwargs(data) -> dict:
    payload = data.model_dump()
    payload["guardian_relationship"] = payload.pop("relationship", "parent")
    return payload


@router.post("/", response_model=StudentResponse)
async def create_student(
    student_data: StudentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    # Check if user already has a student profile
    result = await db.execute(
        select(Student).where(Student.user_id == student_data.user_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User already has a student profile"
        )
    
    # Generate concurrent-safe CMA Registration ID
    cma_id = await CMAIdService.generate_cma_id(db)
    
    # Create student
    student_dict = student_data.model_dump(exclude={"guardians", "instruments"})
    db_student = Student(**student_dict, cma_registration_id=cma_id)
    db.add(db_student)
    await db.flush()
    
    # Create guardians
    for guardian_data in student_data.guardians:
        db_guardian = Guardian(
            student_id=db_student.id,
            **_guardian_kwargs(guardian_data)
        )
        db.add(db_guardian)
    
    # Create instruments
    for instrument_data in student_data.instruments:
        db_instrument = StudentInstrument(
            student_id=db_student.id,
            **instrument_data.model_dump()
        )
        db.add(db_instrument)
    
    await db.flush()
    
    # Calculate and update profile completeness
    await ProfileService.update_profile_complete_flag(db, db_student.id)
    result = await db.execute(
        select(Student).where(Student.id == db_student.id).options(*_student_with_relations())
    )
    return result.scalar_one()


@router.get("/", response_model=List[StudentResponse])
async def list_students(
    skip: int = 0,
    limit: int = 100,
    status: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN, UserRole.INSTRUCTOR]))
):
    query = select(Student).options(*_student_with_relations())

    if current_user.role == UserRole.INSTRUCTOR:
        # instructors only ever see students they are assigned to teach
        from app.services.access import get_instructor_for_user
        instructor = await get_instructor_for_user(db, current_user)
        if not instructor:
            return []
        assigned = await db.execute(
            select(Enrollment.student_id).where(Enrollment.instructor_id == instructor.id)
        )
        ids = list(assigned.scalars().all())
        if not ids:
            return []
        query = query.where(Student.id.in_(ids))

    if status:
        query = query.where(Student.status == status)

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    students = result.scalars().all()
    return students


@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(Student).where(Student.id == student_id).options(*_student_with_relations())
    )
    student = result.scalar_one_or_none()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # self / linked child / assigned instructor / admin only
    await require_student_access(db, current_user, student_id)

    return student


@router.patch("/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: UUID,
    student_data: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    update_data = student_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(student, field, value)
    
    await db.flush()
    result = await db.execute(
        select(Student).where(Student.id == student_id).options(*_student_with_relations())
    )
    return result.scalar_one()


@router.get("/{student_id}/profile", response_model=StudentProfileComplete)
async def get_student_profile_status(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    await require_student_access(db, current_user, student_id)
    
    try:
        profile_status = await ProfileService.check_profile_complete(db, student_id)
        return profile_status
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("/{student_id}/guardians", response_model=GuardianResponse)
async def add_guardian(
    student_id: UUID,
    guardian_data: GuardianCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    # Check student exists
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # Check if student is a minor
    age = await ProfileService.calculate_age(student.date_of_birth)
    
    # Create guardian
    db_guardian = Guardian(
        student_id=student_id,
        **_guardian_kwargs(guardian_data)
    )
    db.add(db_guardian)
    await db.flush()
    
    # Update profile completeness
    await ProfileService.update_profile_complete_flag(db, student_id)
    await db.refresh(db_guardian)
    
    return db_guardian


@router.get("/{student_id}/guardians", response_model=List[GuardianResponse])
async def list_guardians(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check student exists
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # Guardian contact details are personal data: admin, the student themself,
    # or a parent explicitly linked to this student. Teaching staff do not
    # receive guardian PII through this endpoint.
    if current_user.role == UserRole.INSTRUCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view these guardians"
        )
    if current_user.role == UserRole.STUDENT:
        if student.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view these guardians"
            )
    if current_user.role == UserRole.PARENT:
        linked = await get_linked_student_ids(db, current_user)
        if student_id not in linked:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to view these guardians"
            )
    
    result = await db.execute(
        select(Guardian).where(Guardian.student_id == student_id)
    )
    guardians = result.scalars().all()
    return guardians


@router.post("/{student_id}/instruments", response_model=StudentInstrumentResponse)
async def add_instrument(
    student_id: UUID,
    instrument_data: StudentInstrumentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role([UserRole.ADMIN]))
):
    # Check student exists
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    # Check instrument exists
    result = await db.execute(
        select(Instrument).where(Instrument.id == instrument_data.instrument_id)
    )
    instrument = result.scalar_one_or_none()
    
    if not instrument:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Instrument not found"
        )
    
    # Check if student already has this instrument
    result = await db.execute(
        select(StudentInstrument)
        .where(StudentInstrument.student_id == student_id)
        .where(StudentInstrument.instrument_id == instrument_data.instrument_id)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student already has this instrument"
        )
    
    # Create student instrument
    db_student_instrument = StudentInstrument(
        student_id=student_id,
        **instrument_data.model_dump()
    )
    db.add(db_student_instrument)
    await db.flush()
    
    # Update profile completeness
    await ProfileService.update_profile_complete_flag(db, student_id)
    result = await db.execute(
        select(StudentInstrument)
        .where(StudentInstrument.id == db_student_instrument.id)
        .options(selectinload(StudentInstrument.instrument))
    )
    return result.scalar_one()


@router.get("/{student_id}/instruments", response_model=List[StudentInstrumentResponse])
async def list_instruments(
    student_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check student exists
    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found"
        )
    
    await require_student_access(db, current_user, student_id)
    
    result = await db.execute(
        select(StudentInstrument)
        .where(StudentInstrument.student_id == student_id)
        .options(selectinload(StudentInstrument.instrument))
    )
    instruments = result.scalars().all()
    return instruments
