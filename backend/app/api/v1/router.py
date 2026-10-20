from fastapi import APIRouter
from app.api.v1 import (
    auth,
    achievements,
    support,
    students,
    instruments,
    admin,
    registration,
    verify_email,
    sessions,
    billing,
    portal,
    learning,
    remarks,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(students.router, prefix="/students", tags=["students"])
api_router.include_router(instruments.router, prefix="/instruments", tags=["instruments"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(registration.router, tags=["registration"])
api_router.include_router(verify_email.router, tags=["email-verification"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["class-sessions"])
api_router.include_router(billing.router, prefix="/billing", tags=["billing"])
api_router.include_router(portal.router, prefix="/portal", tags=["portal"])
api_router.include_router(learning.router, prefix="/learning", tags=["learning"])
api_router.include_router(remarks.router, prefix="/remarks", tags=["remarks"])
api_router.include_router(support.portal_router, prefix="/portal", tags=["support"])
api_router.include_router(support.admin_router, prefix="/admin", tags=["support"])
api_router.include_router(achievements.portal_router, prefix="/portal", tags=["achievements"])
api_router.include_router(achievements.admin_router, prefix="/admin", tags=["achievements"])
