"""
Admin edit/remove of Resource Recommendations: content+audience updates,
visibility (hide vs delete), target replacement, catalogue deletion with
visibility-grant cleanup, validation and access control.
"""
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_recommendations.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.admin import Admin
from app.models.student import Student
from app.models.learning import ResourceRecommendation, ResourceVisibilityTarget


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    app.dependency_overrides[get_db] = override_get_db
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    app.dependency_overrides.pop(get_db, None)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def admin_user():
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username="resadmin", hashed_password=get_password_hash("0000"),
                 role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=u.id, first_name="Res", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        await s.commit()
        return u


async def _mk_student(username="resstu") -> str:
    async with TestSessionLocal() as s:
        u = User(id=uuid.uuid4(), username=username, hashed_password=get_password_hash("1234"),
                 role=UserRole.STUDENT, is_active=True, must_change_pin=False)
        s.add(u)
        await s.flush()
        st = Student(id=uuid.uuid4(), user_id=u.id, cma_registration_id=f"CMA-2026-{uuid.uuid4().hex[:5].upper()}",
                     portal_slug=f"p{uuid.uuid4().hex[:8]}", first_name="Res", last_name="Stu", status="active")
        s.add(st)
        await s.commit()
        return str(st.id), u.id


def auth(user: User) -> dict:
    tok = create_access_token(data={"sub": str(user.id), "role": user.role.value},
                              expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {tok}"}


async def _create(client, h, **overrides) -> str:
    payload = {"resource_type": "book", "name": "Test Book", "author_or_brand": "Someone"}
    payload.update(overrides)
    r = await client.post("/api/v1/learning/recommendations", json=payload, headers=h)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_edit_updates_content_and_visibility(client, admin_user):
    h = auth(admin_user)
    rid = await _create(client, h, name="Original Title")
    r = await client.patch(f"/api/v1/learning/recommendations/{rid}", json={
        "name": "Edited Title", "description": "Now with details",
        "external_url": "https://example.com/resource"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Edited Title" and r.json()["is_active"] is True

    # staff/admin list reflects edits
    lst = (await client.get("/api/v1/learning/recommendations", headers=h)).json()
    row = next(x for x in lst if x["id"] == rid)
    assert row["name"] == "Edited Title" and row["description"] == "Now with details"
    assert row["is_active"] is True

    # hide it (soft) → still manageable by admin, invisible to students
    r = await client.patch(f"/api/v1/learning/recommendations/{rid}",
                           json={"is_active": False}, headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is False
    lst = (await client.get("/api/v1/learning/recommendations", headers=h)).json()
    row = next(x for x in lst if x["id"] == rid)
    assert row["is_active"] is False                     # admin still sees it (Hidden)
    async with TestSessionLocal() as s:
        n = (await s.execute(select(func_count := __import__("sqlalchemy").func.count())
                             .select_from(ResourceRecommendation)
                             .where(ResourceRecommendation.id == uuid.UUID(rid)))).scalar()
        assert n == 1                                     # hidden ≠ deleted

    # reactivate
    r = await client.patch(f"/api/v1/learning/recommendations/{rid}",
                           json={"is_active": True}, headers=h)
    assert r.status_code == 200 and r.json()["is_active"] is True


@pytest.mark.asyncio
async def test_hidden_invisible_to_students_until_reactivated(client, admin_user):
    h = auth(admin_user)
    sid, stu_uid = await _mk_student("visstu")
    sh = {"Authorization": f"Bearer {create_access_token(data={'sub': str(stu_uid), 'role': 'student'}, expires_delta=timedelta(minutes=30))}"}
    rid = await _create(client, h, name="Visible Book")
    vis = (await client.get("/api/v1/learning/recommendations", headers=sh)).json()
    assert any(x["id"] == rid for x in vis)
    await client.patch(f"/api/v1/learning/recommendations/{rid}", json={"is_active": False}, headers=h)
    vis = (await client.get("/api/v1/learning/recommendations", headers=sh)).json()
    assert all(x["id"] != rid for x in vis)              # hidden from students
    # student payload never carries admin fields
    assert "is_active" not in vis[0] if vis else True
    await client.patch(f"/api/v1/learning/recommendations/{rid}", json={"is_active": True}, headers=h)
    vis = (await client.get("/api/v1/learning/recommendations", headers=sh)).json()
    assert any(x["id"] == rid for x in vis)              # reactivated


@pytest.mark.asyncio
async def test_audience_targets_replace_and_clear(client, admin_user):
    h = auth(admin_user)
    sid1, _ = await _mk_student("tstu1")
    sid2, _ = await _mk_student("tstu2")
    rid = await _create(client, h, name="Targeted Item", visibility_scope="students",
                        target_student_ids=[sid1])
    lst = (await client.get("/api/v1/learning/recommendations", headers=h)).json()
    row = next(x for x in lst if x["id"] == rid)
    assert row["target_student_ids"] == [sid1]
    # replace with sid2
    r = await client.patch(f"/api/v1/learning/recommendations/{rid}",
                           json={"target_student_ids": [sid2]}, headers=h)
    assert r.status_code == 200 and r.json()["target_students"] == 1
    lst = (await client.get("/api/v1/learning/recommendations", headers=h)).json()
    assert next(x for x in lst if x["id"] == rid)["target_student_ids"] == [sid2]
    # clear (empty list) → scope back to all for safety of the demo
    r = await client.patch(f"/api/v1/learning/recommendations/{rid}",
                           json={"target_student_ids": [], "visibility_scope": "all"}, headers=h)
    assert r.status_code == 200
    lst = (await client.get("/api/v1/learning/recommendations", headers=h)).json()
    assert next(x for x in lst if x["id"] == rid)["target_student_ids"] == []


@pytest.mark.asyncio
async def test_delete_removes_grants_and_row(client, admin_user):
    h = auth(admin_user)
    sid, _ = await _mk_student("dstu")
    rid = await _create(client, h, name="To Be Removed", visibility_scope="students",
                        target_student_ids=[sid])
    async with TestSessionLocal() as s:
        grants = (await s.execute(select(ResourceVisibilityTarget).where(
            ResourceVisibilityTarget.resource_id == uuid.UUID(rid)))).scalars().all()
        assert len(grants) == 1
    r = await client.delete(f"/api/v1/learning/recommendations/{rid}", headers=h)
    assert r.status_code == 200 and r.json()["deleted"] is True
    async with TestSessionLocal() as s:
        assert (await s.execute(select(ResourceRecommendation).where(
            ResourceRecommendation.id == uuid.UUID(rid)))).scalar_one_or_none() is None
        grants = (await s.execute(select(ResourceVisibilityTarget).where(
            ResourceVisibilityTarget.resource_id == uuid.UUID(rid)))).scalars().all()
        assert grants == []                                 # no orphaned grants
        from app.models.audit import AuditEvent
        ev = (await s.execute(select(AuditEvent).where(
            AuditEvent.action == "recommendation.deleted"))).scalars().all()
        assert ev and rid in (ev[-1].entity_id or "")
    # second delete →404
    r = await client.delete(f"/api/v1/learning/recommendations/{rid}", headers=h)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_validation_and_access_control(client, admin_user):
    h = auth(admin_user)
    rid = await _create(client, h)
    # https enforced
    r = await client.patch(f"/api/v1/learning/recommendations/{rid}",
                           json={"external_url": "http://insecure.example"}, headers=h)
    assert r.status_code == 400
    # unknown ids
    r = await client.patch(f"/api/v1/learning/recommendations/{uuid.uuid4()}",
                           json={"name": "x y"}, headers=h)
    assert r.status_code == 404
    r = await client.delete(f"/api/v1/learning/recommendations/{uuid.uuid4()}", headers=h)
    assert r.status_code == 404
    # students cannot edit or delete
    _, stu_uid = await _mk_student("attacker")
    sh = {"Authorization": f"Bearer {create_access_token(data={'sub': str(stu_uid), 'role': 'student'}, expires_delta=timedelta(minutes=30))}"}
    r = await client.patch(f"/api/v1/learning/recommendations/{rid}", json={"name": "hacked"}, headers=sh)
    assert r.status_code == 403
    r = await client.delete(f"/api/v1/learning/recommendations/{rid}", headers=sh)
    assert r.status_code == 403
    # name length validated by schema
    r = await client.patch(f"/api/v1/learning/recommendations/{rid}", json={"name": "x"}, headers=h)
    assert r.status_code == 422
    # create with bad url still blocked
    r = await client.post("/api/v1/learning/recommendations",
                          json={"resource_type": "online_link", "name": "Bad Link",
                                "external_url": "ftp://nope"}, headers=h)
    assert r.status_code == 400
