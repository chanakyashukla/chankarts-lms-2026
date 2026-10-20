"""
Admin seed utility.
Creates the initial admin user if SEED_ADMIN_* env vars are set.
Idempotent — safe to run on every startup.
"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.models.admin import Admin
from app.core.roles import UserRole
from app.core.security import get_password_hash
from app.config import get_settings

logger = logging.getLogger(__name__)


async def seed_admin(db: AsyncSession) -> None:
    settings = get_settings()

    email = settings.SEED_ADMIN_EMAIL.strip()
    username = settings.SEED_ADMIN_USERNAME.strip()
    password = settings.SEED_ADMIN_PASSWORD.strip()

    if not email or not username or not password:
        logger.info("Seed admin: SEED_ADMIN_EMAIL/USERNAME/PASSWORD not set, skipping")
        return

    # Check if admin user already exists
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()

    if existing:
        logger.info(f"Seed admin: user {email} already exists (id={existing.id}), skipping")
        return

    # Create User with admin role
    user = User(
        email=email,
        username=username,
        hashed_password=get_password_hash(password),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(user)
    await db.flush()

    # Create Admin profile
    admin_profile = Admin(
        user_id=user.id,
        first_name=settings.SEED_ADMIN_FIRST_NAME or "Admin",
        last_name=settings.SEED_ADMIN_LAST_NAME or "User",
        admin_level="super_admin",
        is_active=True,
    )
    db.add(admin_profile)
    await db.flush()

    logger.info(f"Seed admin: created user {email} (id={user.id}, role=admin)")
