"""
Central authorization helpers.

Every portal request resolves access through these functions on the server;
personalised URLs, roll numbers and hidden buttons are never trusted.
"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.core.roles import UserRole
from app.models.user import User
from app.models.student import Student
from app.models.guardian import GuardianAccount
from app.models.instructor import Instructor
from app.models.enrollment import Enrollment


async def get_student_profile_for_user(db: AsyncSession, user: User) -> Optional[Student]:
    if user.role != UserRole.STUDENT:
        return None
    result = await db.execute(select(Student).where(Student.user_id == user.id))
    return result.scalar_one_or_none()


async def get_linked_student_ids(db: AsyncSession, user: User) -> List[UUID]:
    """Student ids the user may view: own profile or explicitly linked children."""
    if user.role == UserRole.STUDENT:
        student = await get_student_profile_for_user(db, user)
        return [student.id] if student else []

    if user.role == UserRole.PARENT:
        result = await db.execute(
            select(GuardianAccount.student_id).where(GuardianAccount.user_id == user.id)
        )
        return list(result.scalars().all())

    return []  # admins/instructors use their own scoped queries


async def can_access_student(db: AsyncSession, user: User, student_id: UUID) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    if user.role in (UserRole.STUDENT, UserRole.PARENT):
        return student_id in await get_linked_student_ids(db, user)
    if user.role == UserRole.INSTRUCTOR:
        instructor = await get_instructor_for_user(db, user)
        if not instructor:
            return False
        result = await db.execute(
            select(Enrollment.id).where(
                Enrollment.student_id == student_id,
                Enrollment.instructor_id == instructor.id,
            )
        )
        return result.scalar_one_or_none() is not None
    return False


async def require_student_access(db: AsyncSession, user: User, student_id: UUID) -> None:
    if not await can_access_student(db, user, student_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this student's records",
        )


async def get_instructor_for_user(db: AsyncSession, user: User) -> Optional[Instructor]:
    if user.role != UserRole.INSTRUCTOR:
        return None
    result = await db.execute(select(Instructor).where(Instructor.user_id == user.id))
    return result.scalar_one_or_none()


async def get_default_student_id(db: AsyncSession, user: User) -> Optional[UUID]:
    """For students/parents with one linked child, a convenient default."""
    ids = await get_linked_student_ids(db, user)
    return ids[0] if ids else None


async def get_enrollments_for_student(
    db: AsyncSession, student_id: UUID, active_only: bool = False
) -> List[Enrollment]:
    query = select(Enrollment).where(Enrollment.student_id == student_id)
    if active_only:
        query = query.where(Enrollment.status == "active")
    query = query.order_by(Enrollment.created_at.asc())
    result = await db.execute(query)
    return list(result.scalars().all())
