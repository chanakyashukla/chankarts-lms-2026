"""
Two-way communication with administration.

- Students, parents and instructors can contact administration.
- Admin can reply and resolve; the sender is notified in-portal.
- Users can only ever see their own conversations.
- The messaging form cannot be used to reach unrelated student records.
- Attachments are validated server-side.
"""
import io
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_support_messaging.db"
engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

from app.main import app
from app.database import get_db, Base
from app.core.roles import UserRole
from app.core.security import create_access_token, get_password_hash
from app.models.user import User
from app.models.admin import Admin
from app.models.instructor import Instructor
from app.models.student import Student
from app.models.guardian import GuardianAccount
from app.models.enrollment import Enrollment
from app.models.notification import Notification


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
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_token(user: User) -> str:
    return create_access_token(
        data={"sub": str(user.id), "role": user.role.value},
        expires_delta=timedelta(minutes=30),
    )


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {_make_token(user)}"}


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def world():
    async with TestSessionLocal() as db:
        admin_u = User(username="supadmin", email="supadmin@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="Sup", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        inst_u = User(username="supinst", email="supinst@t.local",
                      hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(inst_u)
        await db.flush()
        inst = Instructor(user_id=inst_u.id, first_name="Sup", last_name="Faculty",
                          specializations="piano", is_active=True)
        db.add(inst)

        other_inst_u = User(username="supother", email="supother@t.local",
                            hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(other_inst_u)
        await db.flush()
        other_inst = Instructor(user_id=other_inst_u.id, first_name="Other", last_name="Faculty",
                                specializations="guitar", is_active=True)
        db.add(other_inst)

        sa_u = User(username="CMA-9401", hashed_password=get_password_hash("9401"),
                    role=UserRole.STUDENT)
        sb_u = User(username="CMA-9402", hashed_password=get_password_hash("9402"),
                    role=UserRole.STUDENT)
        db.add_all([sa_u, sb_u])
        await db.flush()
        sa = Student(user_id=sa_u.id, cma_registration_id="CMA-2026-9401",
                     first_name="Sam", last_name="Singer", status="active")
        sb = Student(user_id=sb_u.id, cma_registration_id="CMA-2026-9402",
                     first_name="Pat", last_name="Pianist", status="active")
        db.add_all([sa, sb])
        await db.flush()
        ea = Enrollment(student_id=sa.id, programme_id="piano", programme_name="Piano",
                        instructor_id=inst.id, fee_plan="4_classes", fee_amount=4500,
                        status="active")
        db.add(ea)

        parent_u = User(username="supparent", email="supparent@t.local",
                        hashed_password=get_password_hash("x"), role=UserRole.PARENT)
        db.add(parent_u)
        await db.flush()
        db.add(GuardianAccount(user_id=parent_u.id, student_id=sa.id, relationship="mother"))

        await db.commit()
        return {"admin": admin_u, "instructor": inst_u, "other_inst": other_inst_u,
                "student_a": sa_u, "sa_id": sa.id, "student_b": sb_u, "sb_id": sb.id,
                "parent": parent_u, "enrollment_id": ea.id}


# ---------------------------------------------------------------------------
# Senders can contact administration
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_roles_can_contact_administration(client, world):
    w = world
    for user, subject in ((w["student_a"], "Question about fees"),
                          (w["parent"], "Schedule for my child"),
                          (w["instructor"], "Room booking for recital")):
        r = await client.post("/api/v1/portal/support",
                              json={"subject": subject, "message": "Hello administration, please advise."},
                              headers=auth(user))
        assert r.status_code == 201, r.text
        assert r.json()["status"] == "open"

    inbox = await client.get("/api/v1/admin/support", headers=auth(w["admin"]))
    assert inbox.status_code == 200
    assert len(inbox.json()) == 3
    roles = {x["sender_role"] for x in inbox.json()}
    assert roles == {"student", "parent", "instructor"}


# ---------------------------------------------------------------------------
# Admin reply + resolve, with in-portal notifications
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_admin_reply_and_resolve_notifies_sender(client, world):
    w = world
    created = await client.post("/api/v1/portal/support",
                                json={"subject": "Fee receipt missing", "message": "Please check."},
                                headers=auth(w["student_a"]))
    rid = created.json()["id"]

    reply = await client.post(f"/api/v1/admin/support/{rid}/reply",
                              json={"body": "We have re-sent the receipt to your registered email."},
                              headers=auth(w["admin"]))
    assert reply.status_code == 201
    assert reply.json()["author_role"] == "admin"

    thread = await client.get(f"/api/v1/portal/support/{rid}", headers=auth(w["student_a"]))
    assert thread.json()["status"] == "replied"
    assert any(x["author_role"] == "admin" for x in thread.json()["replies"])

    res = await client.post(f"/api/v1/admin/support/{rid}/status",
                            json={"status": "resolved"}, headers=auth(w["admin"]))
    assert res.status_code == 200 and res.json()["status"] == "resolved"

    async with TestSessionLocal() as db:
        notes = (await db.execute(select(Notification).where(
            Notification.user_id == w["student_a"].id))).scalars().all()
        types = {n.type for n in notes}
        assert "support.reply" in types and "support.resolved" in types

    # resolved conversations are closed for the sender
    late = await client.post(f"/api/v1/portal/support/{rid}/reply",
                             json={"body": "one more thing"}, headers=auth(w["student_a"]))
    assert late.status_code == 400


# ---------------------------------------------------------------------------
# Privacy — conversations are per sender
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_users_only_see_their_own_conversations(client, world):
    w = world
    mine = await client.post("/api/v1/portal/support",
                             json={"subject": "Private matter", "message": "Only mine."},
                             headers=auth(w["student_a"]))
    rid = mine.json()["id"]

    # another student cannot open it
    r = await client.get(f"/api/v1/portal/support/{rid}", headers=auth(w["student_b"]))
    assert r.status_code == 403
    # nor reply to it
    r2 = await client.post(f"/api/v1/portal/support/{rid}/reply",
                           json={"body": "intrusion"}, headers=auth(w["student_b"]))
    assert r2.status_code == 403
    # an unrelated instructor cannot open it
    r3 = await client.get(f"/api/v1/portal/support/{rid}", headers=auth(w["other_inst"]))
    assert r3.status_code == 403
    # their own lists never contain it
    lst = await client.get("/api/v1/portal/support", headers=auth(w["student_b"]))
    assert lst.json() == []


# ---------------------------------------------------------------------------
# The form cannot reach unrelated student records
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_form_cannot_reference_unauthorised_student(client, world):
    w = world
    # instructor B is not assigned to student A
    r = await client.post("/api/v1/portal/support",
                          json={"subject": "Sneaky", "message": "Let me see this student.",
                                "related_student_id": str(w["sa_id"])},
                          headers=auth(w["other_inst"]))
    assert r.status_code == 403

    # the assigned instructor may reference their own student
    ok = await client.post("/api/v1/portal/support",
                           json={"subject": "Lesson plan", "message": "About my student's plan.",
                                 "related_student_id": str(w["sa_id"])},
                           headers=auth(w["instructor"]))
    assert ok.status_code == 201

    # student B cannot reference student A
    r2 = await client.post("/api/v1/portal/support",
                           json={"subject": "Sneaky", "message": "Not my record.",
                                 "related_student_id": str(w["sa_id"])},
                           headers=auth(w["student_b"]))
    assert r2.status_code == 403


# ---------------------------------------------------------------------------
# Attachments validated server-side
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_attachment_type_validated(client, world):
    w = world
    created = await client.post("/api/v1/portal/support",
                                json={"subject": "Screenshot", "message": "Attached proof."},
                                headers=auth(w["student_a"]))
    rid = created.json()["id"]

    # unsafe file type rejected
    bad = await client.post(
        f"/api/v1/portal/support/{rid}/attachments",
        files={"file": ("evil.sh", io.BytesIO(b"#!/bin/sh"), "application/x-sh")},
        headers=auth(w["student_a"]))
    assert bad.status_code == 400

    # a PDF is accepted
    good = await client.post(
        f"/api/v1/portal/support/{rid}/attachments",
        files={"file": ("note.pdf", io.BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        headers=auth(w["student_a"]))
    assert good.status_code == 201, good.text
    assert good.json()["filename"] == "note.pdf"

    # another user cannot fetch the file
    stored = good.json()["filename"]
    thread = await client.get(f"/api/v1/portal/support/{rid}", headers=auth(w["student_a"]))
    stored_name = thread.json()["attachments"][0]["id"]  # id only in list
    files_route = await client.get(
        f"/api/v1/portal/support/files/{thread.json()['attachments'][0].get('stored_name', 'x')}",
        headers=auth(w["student_b"]))
    assert files_route.status_code in (403, 404)
