from datetime import date
from typing import List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.student import Student
from app.models.guardian import Guardian
from app.models.instrument import StudentInstrument
from app.schemas.student import StudentProfileComplete


class ProfileService:
    """Service for student profile management and completeness checking."""
    
    @staticmethod
    async def calculate_age(date_of_birth: date) -> int:
        today = date.today()
        age = today.year - date_of_birth.year - (
            (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
        )
        return age
    
    @staticmethod
    async def check_profile_complete(
        db: AsyncSession,
        student_id: UUID
    ) -> StudentProfileComplete:
        result = await db.execute(
            select(Student).where(Student.id == student_id)
        )
        student = result.scalar_one_or_none()
        
        if not student:
            raise ValueError("Student not found")
        
        # Check required fields
        missing_fields = []
        if not student.first_name:
            missing_fields.append("first_name")
        if not student.last_name:
            missing_fields.append("last_name")
        if not student.date_of_birth:
            missing_fields.append("date_of_birth")
        
        # Check guardians (required for minors)
        age = await ProfileService.calculate_age(student.date_of_birth)
        guardians_result = await db.execute(
            select(Guardian).where(Guardian.student_id == student_id)
        )
        guardians = guardians_result.scalars().all()
        has_guardians = len(guardians) > 0
        
        if age < 18 and not has_guardians:
            missing_fields.append("guardians (required for minors)")
        
        # Check instruments
        instruments_result = await db.execute(
            select(StudentInstrument).where(StudentInstrument.student_id == student_id)
        )
        instruments = instruments_result.scalars().all()
        has_instruments = len(instruments) > 0
        
        if not has_instruments:
            missing_fields.append("at least one instrument/discipline")
        
        profile_complete = len(missing_fields) == 0
        
        return StudentProfileComplete(
            student_id=student.id,
            cma_registration_id=student.cma_registration_id,
            profile_complete=profile_complete,
            missing_fields=missing_fields,
            has_guardians=has_guardians,
            has_instruments=has_instruments,
            age=age,
        )
    
    @staticmethod
    async def update_profile_complete_flag(
        db: AsyncSession,
        student_id: UUID
    ) -> bool:
        profile_status = await ProfileService.check_profile_complete(db, student_id)
        
        result = await db.execute(
            select(Student).where(Student.id == student_id)
        )
        student = result.scalar_one_or_none()
        
        if student:
            student.profile_complete = profile_status.profile_complete
            await db.flush()
            return profile_status.profile_complete
        
        return False
