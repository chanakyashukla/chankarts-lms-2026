"""
Phase 7 — Admin operational console endpoints:
  - /admin/progress (syllabus + reports overview)
  - /admin/audit (audit trail)
  - /admin/settings (non-secret operational config + fee packages)
  - POST /billing/packages (admin-only upsert)
"""
import pytest
import pytest_asyncio

from tests.test_phase5 import (  # noqa: F401 — re-used fixtures
    client,
    admin_user,
    instructor_user,
    student_user,
    enrollment,
    auth,
)
from tests.test_phase5 import _make_token, engine as phase5_engine
from app.database import Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create/drop schema on the shared phase5 test engine (fixtures come from that module)."""
    async with phase5_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with phase5_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def parent_user():
    from tests.test_phase5 import TestSessionLocal

    async with TestSessionLocal() as session:
        user = User(
            email="parent7@test.com",
            username="parent7",
            hashed_password=get_password_hash("ParentPass@123"),
            role=UserRole.PARENT,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        return user


@pytest.mark.asyncio
async def test_admin_settings_hides_secrets(client, admin_user, parent_user):
    resp = await client.get("/api/v1/admin/settings", headers=auth(admin_user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["timezone"] == "Asia/Kolkata"
    assert body["currency"] == "INR"
    assert isinstance(body["fee_packages"], list)
    assert body["razorpay"]["enabled"] in (True, False)
    # never leak secret material
    raw = resp.text.lower()
    for banned in ("secret", "password", "access_key", "webhook_secret", "api_key"):
        assert banned not in raw, f"settings response leaks '{banned}'"

    # non-admin roles are refused
    from tests.test_phase5 import student_user as _su  # noqa

    for user in (parent_user,):
        tok = create_access_token(data={"sub": str(user.id), "role": user.role.value})
        r = await client.get("/api/v1/admin/settings", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_admin_progress_overview(client, admin_user, instructor_user, student_user, enrollment):
    resp = await client.get("/api/v1/admin/progress", headers=auth(admin_user))
    assert resp.status_code == 200, resp.text
    rows = resp.json()["students"]
    match = [r for r in rows if r["student_name"] == "Ira Sen"]
    assert match, rows
    row = match[0]
    assert row["syllabus_completed"] == 0
    assert row["syllabus_total"] == 0
    assert row["syllabus_percent"] is None
    assert row["latest_report"] is None
    assert row["pending_assignments"] == 0

    # student role blocked on admin endpoints
    tok = create_access_token(data={"sub": str(student_user.id), "role": student_user.role.value})
    r = await client.get("/api/v1/admin/progress", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_audit_trail(client, admin_user):
    resp = await client.get("/api/v1/admin/audit", headers=auth(admin_user))
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)

    filtered = await client.get(
        "/api/v1/admin/audit?action_prefix=registration&limit=10", headers=auth(admin_user)
    )
    assert filtered.status_code == 200
    for event in filtered.json():
        assert event["action"].startswith("registration")


@pytest.mark.asyncio
async def test_admin_fee_package_upsert(client, admin_user, instructor_user, parent_user):
    payload = {
        "code": "custom_evening",
        "name": "Evening Special (admin)",
        "sessions_included": 6,
        "fee_paise": 650000,
        "session_duration_minutes": 60,
        "description": "Individually agreed evening batch",
        "is_legacy": True,
    }
    created = await client.post("/api/v1/billing/packages", json=payload, headers=auth(admin_user))
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "custom_evening"
    assert created.json()["fee_paise"] == 650000

    # upsert (same code) keeps a single package
    payload["fee_paise"] = 700000
    updated = await client.post("/api/v1/billing/packages", json=payload, headers=auth(admin_user))
    assert updated.status_code == 201
    assert updated.json()["id"] == created.json()["id"]
    assert updated.json()["fee_paise"] == 700000

    settings_resp = await client.get("/api/v1/admin/settings", headers=auth(admin_user))
    codes = [p["code"] for p in settings_resp.json()["fee_packages"]]
    assert codes.count("custom_evening") == 1

    # non-admin roles refused
    tok = create_access_token(
        data={"sub": str(instructor_user.id), "role": instructor_user.role.value}
    )
    r = await client.post(
        "/api/v1/billing/packages", json=payload, headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 403

    bad = await client.post(
        "/api/v1/billing/packages",
        json={**payload, "code": "Custom Evening!"},  # invalid pattern
        headers=auth(admin_user),
    )
    assert bad.status_code == 422
