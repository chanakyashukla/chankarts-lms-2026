"""
Phase 7 — Additional remarks with explicit visibility.
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
    _make_token,
)
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.database import Base
from tests.test_phase5 import engine as phase5_engine


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create/drop schema on the shared phase5 test engine (fixtures come from that module)."""
    async with phase5_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with phase5_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def parent_user_linked(admin_user, student_user):
    from tests.test_phase5 import TestSessionLocal
    from sqlalchemy import select
    from app.models.student import Student
    from app.models.guardian import GuardianAccount

    async with TestSessionLocal() as session:
        user = User(
            email="parent_remark@test.com",
            username="parent_remark",
            hashed_password=get_password_hash("ParentPass@123"),
            role=UserRole.PARENT,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        student_result = await session.execute(select(Student).where(Student.user_id == student_user.id))
        student = student_result.scalar_one()
        session.add(GuardianAccount(user_id=user.id, student_id=student.id))
        await session.commit()
        return user


@pytest.mark.asyncio
async def test_remark_visibility_is_explicit_and_enforced(
    client, admin_user, student_user, parent_user_linked, enrollment
):
    from sqlalchemy import select
    from tests.test_phase5 import TestSessionLocal
    from app.models.student import Student

    async with TestSessionLocal() as session:
        student_result = await session.execute(select(Student).where(Student.user_id == student_user.id))
        student = student_result.scalar_one()
        student_id = str(student.id)

    admin_tok = auth(admin_user)
    student_tok = {"Authorization": f"Bearer {_make_token(student_user)}"}
    parent_tok = {"Authorization": f"Bearer {_make_token(parent_user_linked)}"}

    # 1. Student-visible remark — visible to admin (as staff, opt-in false => still shown since not staff_only), student, parent? No — parent only sees parent_visible.
    r1 = await client.post(
        "/api/v1/remarks",
        json={"student_id": student_id, "visibility": "student_visible", "body": "Great improvement on scales this month."},
        headers=admin_tok,
    )
    assert r1.status_code == 201, r1.text

    # 2. Parent-visible remark
    r2 = await client.post(
        "/api/v1/remarks",
        json={"student_id": student_id, "visibility": "parent_visible", "body": "Please ensure practice log is signed weekly."},
        headers=admin_tok,
    )
    assert r2.status_code == 201, r2.text

    # 3. Staff-only remark
    r3 = await client.post(
        "/api/v1/remarks",
        json={"student_id": student_id, "visibility": "staff_only", "body": "Internal: consider level change next term."},
        headers=admin_tok,
    )
    assert r3.status_code == 201, r3.text

    # Student sees only student_visible
    s_list = await client.get(f"/api/v1/remarks?student_id={student_id}", headers=student_tok)
    assert s_list.status_code == 200, s_list.text
    s_bodies = [r["body"] for r in s_list.json()]
    assert "Great improvement on scales this month." in s_bodies
    assert "Please ensure practice log is signed weekly." not in s_bodies
    assert "Internal: consider level change next term." not in s_bodies
    s_vis = {r["visibility"] for r in s_list.json()}
    assert s_vis == {"student_visible"}

    # Parent sees only parent_visible
    p_list = await client.get(f"/api/v1/remarks?student_id={student_id}", headers=parent_tok)
    assert p_list.status_code == 200, p_list.text
    p_bodies = [r["body"] for r in p_list.json()]
    assert "Please ensure practice log is signed weekly." in p_bodies
    assert "Great improvement on scales this month." not in p_bodies
    assert "Internal: consider level change next term." not in p_bodies
    p_vis = {r["visibility"] for r in p_list.json()}
    assert p_vis == {"parent_visible"}

    # Admin default listing excludes staff_only
    a_list = await client.get(f"/api/v1/remarks?student_id={student_id}", headers=admin_tok)
    assert a_list.status_code == 200
    a_bodies = [r["body"] for r in a_list.json()]
    assert "Internal: consider level change next term." not in a_bodies

    # Admin opt-in sees staff_only too
    a_all = await client.get(f"/api/v1/remarks?student_id={student_id}&include_staff_only=true", headers=admin_tok)
    assert a_all.status_code == 200
    a_all_bodies = [r["body"] for r in a_all.json()]
    assert "Internal: consider level change next term." in a_all_bodies

    # 4. Edit a remark (visibility flip + body change), verify persistence and audit history
    remark_id = r1.json()["id"]
    upd = await client.patch(
        f"/api/v1/remarks/{remark_id}",
        json={"visibility": "parent_visible", "body": "Updated: excellent scales progress."},
        headers=admin_tok,
    )
    assert upd.status_code == 200, upd.text
    assert upd.json()["visibility"] == "parent_visible"
    assert upd.json()["body"] == "Updated: excellent scales progress."

    # Student no longer sees it (was student_visible, now parent_visible)
    s_list2 = await client.get(f"/api/v1/remarks?student_id={student_id}", headers=student_tok)
    assert "Updated: excellent scales progress." not in [r["body"] for r in s_list2.json()]

    # Parent now sees it
    p_list2 = await client.get(f"/api/v1/remarks?student_id={student_id}", headers=parent_tok)
    assert "Updated: excellent scales progress." in [r["body"] for r in p_list2.json()]

    # Audit history shows both create and update events
    hist = await client.get(f"/api/v1/remarks/{remark_id}/history", headers=admin_tok)
    assert hist.status_code == 200, hist.text
    actions = [e["action"] for e in hist.json()]
    assert "remark.created" in actions
    assert "remark.updated" in actions

    # 5. Non-staff cannot create remarks
    bad_student = await client.post(
        "/api/v1/remarks",
        json={"student_id": student_id, "visibility": "student_visible", "body": "nope"},
        headers=student_tok,
    )
    assert bad_student.status_code == 403

    # 6. Unlinked parent (no guardian account link) gets 403 on this student
    from tests.test_phase7_admin import parent_user as _unused  # noqa

    # A fresh parent with no link
    async with TestSessionLocal() as session:
        orphan = User(
            email="orphan_parent@test.com",
            username="orphan_parent",
            hashed_password=get_password_hash("ParentPass@123"),
            role=UserRole.PARENT,
            is_active=True,
        )
        session.add(orphan)
        await session.commit()
    orphan_tok = {"Authorization": f"Bearer {_make_token(orphan)}"}
    r = await client.get(f"/api/v1/remarks?student_id={student_id}", headers=orphan_tok)
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_instructor_cannot_remark_on_untaught_student(client, admin_user, instructor_user, student_user):
    from sqlalchemy import select
    from tests.test_phase5 import TestSessionLocal
    from app.models.student import Student

    async with TestSessionLocal() as session:
        student_result = await session.execute(select(Student).where(Student.user_id == student_user.id))
        student = student_result.scalar_one()
        student_id = str(student.id)

    # instructor_user has no enrollment for this student (enrollment fixture not used here)
    r = await client.post(
        "/api/v1/remarks",
        json={"student_id": student_id, "visibility": "staff_only", "body": "should fail"},
        headers=auth(instructor_user),
    )
    assert r.status_code == 403
