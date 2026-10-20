"""Audit trail helper — records who changed what, without secrets."""
from typing import Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit import AuditEvent


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: Any,
    actor_user_id: Optional[UUID] = None,
    actor_role: Optional[str] = None,
    summary: Optional[str] = None,
    before_data: Optional[dict] = None,
    after_data: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> AuditEvent:
    event = AuditEvent(
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=summary,
        before_data=before_data,
        after_data=after_data,
        ip_address=ip_address,
    )
    db.add(event)
    await db.flush()
    return event
