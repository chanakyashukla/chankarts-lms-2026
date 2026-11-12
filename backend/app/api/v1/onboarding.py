"""Interactive guided-tour / onboarding state for portal users.

Server-side source of truth for first-login introductions (spec: never rely
exclusively on browser localStorage, so state follows the account across
devices). Self-scoped: a user can only ever read or update their own record —
identity comes from the bearer token, never from the request body.
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User

router = APIRouter()

# Bump when tour content changes substantially; old records keep their version
# so existing users are not re-interrupted by content updates (spec §6).
ONBOARDING_CONTENT_VERSION = "2026-11-09"


def _default_state() -> dict:
    return {
        "version": ONBOARDING_CONTENT_VERSION,
        "shown": False,
        "started": False,
        "completed": False,
        "skipped": False,
        "progress": None,
        "updated_at": None,
    }


def _normalise(raw: Optional[dict]) -> dict:
    state = _default_state()
    if isinstance(raw, dict):
        for key in ("version", "shown", "started", "completed", "skipped", "progress", "updated_at"):
            if key in raw:
                state[key] = raw[key]
    return state


class OnboardingUpdate(BaseModel):
    """Partial update — only fields explicitly provided are merged in."""

    version: Optional[str] = Field(None, max_length=64)
    shown: Optional[bool] = None
    started: Optional[bool] = None
    completed: Optional[bool] = None
    skipped: Optional[bool] = None
    progress: Optional[dict] = None

    @field_validator("progress")
    @classmethod
    def _validate_progress(cls, value):
        if value is None:
            return value
        step = value.get("step")
        if step is not None and (not isinstance(step, int) or isinstance(step, bool) or step < 0):
            raise ValueError("progress.step must be a non-negative integer")
        tour = value.get("tour")
        if tour is not None and (not isinstance(tour, str) or len(tour) > 64):
            raise ValueError("progress.tour must be a short string")
        return value


@router.get("")
async def get_onboarding(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Read the caller's own onboarding/tour state (any portal role)."""
    return _normalise(current_user.onboarding)


@router.put("")
async def update_onboarding(
    body: OnboardingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the caller's own onboarding/tour state.

    Only the authenticated user's row is ever touched — there is no user id
    in the path or body, so one account cannot alter another's state.
    Explicit ``null`` clears a field (e.g. progress on tour completion);
    omitted fields are left untouched.
    """
    state = _normalise(current_user.onboarding)
    provided = body.model_fields_set
    changed = False
    for key in ("version", "shown", "started", "completed", "skipped", "progress"):
        if key not in provided:
            continue
        incoming = getattr(body, key)
        if incoming != state[key]:
            state[key] = incoming
            changed = True
    if changed:
        state["updated_at"] = datetime.utcnow().isoformat() + "Z"
        current_user.onboarding = state
        db.add(current_user)
        await db.flush()
    return _normalise(current_user.onboarding)
