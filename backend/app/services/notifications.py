"""
Notification service.

Creates in-app notifications (and optionally queues an email) with a unique
`dedupe_key` so retried jobs/webhooks never duplicate a message. Email
delivery is delegated to EmailService and is skipped when not configured.
"""
import logging
from typing import Optional
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.notification import Notification
from app.services.email import email_service

logger = logging.getLogger(__name__)


async def notify_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    type: str,
    title: str,
    body: str = "",
    dedupe_key: Optional[str] = None,
    related_entity_type: Optional[str] = None,
    related_entity_id: Optional[str] = None,
    send_email: bool = False,
    email_address: Optional[str] = None,
) -> Optional[Notification]:
    """Create a notification exactly once for a given dedupe_key."""
    if dedupe_key:
        existing = await db.execute(
            select(Notification).where(Notification.dedupe_key == dedupe_key)
        )
        if existing.scalar_one_or_none():
            return None

    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        body=body,
        dedupe_key=dedupe_key,
        related_entity_type=related_entity_type,
        related_entity_id=str(related_entity_id) if related_entity_id is not None else None,
        status="pending",
    )
    db.add(notification)
    await db.flush()

    if send_email and email_address:
        try:
            delivered = email_service.send_simple_email(
                to_email=email_address,
                subject=title,
                text_body=body or title,
            )
            notification.status = "sent" if delivered else "failed"
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Notification email failed: %s", exc)
            notification.status = "failed"
    await db.flush()
    return notification


async def mark_notifications_read(db: AsyncSession, user_id: UUID) -> int:
    from datetime import datetime
    result = await db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.read_at.is_(None),
        )
    )
    count = 0
    for notification in result.scalars().all():
        notification.read_at = datetime.utcnow()
        count += 1
    await db.flush()
    return count
