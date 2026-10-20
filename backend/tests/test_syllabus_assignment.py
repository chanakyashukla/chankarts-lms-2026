"""
Admin-controlled, student-specific syllabus assignments.

- A syllabus assigned to one student is invisible to other students.
- Parents see only linked children's syllabi; instructors only their students'.
- Different syllabi can be assigned to two students on the same instrument.
- API endpoints cannot be used to bypass the visibility rules.
- Archiving an assignment removes the syllabus from that student's view.
"""
import uuid
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_syllabus_assignment.db"
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
    """Two students on the SAME instrument, two instructors, two parents."""
    async with TestSessionLocal() as db:
        admin_u = User(username="saadmin", email="saadmin@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="SA", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        def mk_inst(username):
            u = User(username=username, email=f"{username}@t.local",
                     hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
            db.add(u)
            return u

        inst_a_u = mk_inst("sainsta")
        inst_b_u = mk_inst("sainstb")
        await db.flush()
        inst_a = Instructor(user_id=inst_a_u.id, first_name="Teach", last_name="A",
                            specializations="piano", is_active=True)
        inst_b = Instructor(user_id=inst_b_u.id, first_name="Teach", last_name="B",
                            specializations="piano", is_active=True)
        db.add_all([inst_a, inst_b])

        def mk_student(username, first):
            u = User(username=username, hashed_password=get_password_hash(username),
                     role=UserRole.STUDENT)
            db.add(u)
            return u, first

        sa_u, _ = mk_student("CMA-9301", "Ann")
        sb_u, _ = mk_student("CMA-9302", "Bob")
        await db.flush()
        sa = Student(user_id=sa_u.id, cma_registration_id="CMA-2026-9301",
                     first_name="Ann", last_name="Keys", status="active")
        sb = Student(user_id=sb_u.id, cma_registration_id="CMA-2026-9302",
                     first_name="Bob", last_name="Chords", status="active")
        db.add_all([sa, sb])
        await db.flush()

        # both study piano — with different plans
        ea = Enrollment(student_id=sa.id, programme_id="piano", programme_name="Piano",
                        instructor_id=inst_a.id, fee_plan="4_classes", fee_amount=4500,
                        status="active")
        eb = Enrollment(student_id=sb.id, programme_id="piano", programme_name="Piano",
                        instructor_id=inst_b.id, fee_plan="8_classes", fee_amount=8000,
                        status="active")
        db.add_all([ea, eb])

        pa_u = User(username="saparenta", email="saparenta@t.local",
                    hashed_password=get_password_hash("x"), role=UserRole.PARENT)
        pb_u = User(username="saparentb", email="saparentb@t.local",
                    hashed_password=get_password_hash("x"), role=UserRole.PARENT)
        db.add_all([pa_u, pb_u])
        await db.flush()
        db.add(GuardianAccount(user_id=pa_u.id, student_id=sa.id, relationship="mother"))
        db.add(GuardianAccount(user_id=pb_u.id, student_id=sb.id, relationship="father"))

        await db.commit()
        return {"admin": admin_u,
                "inst_a": inst_a_u, "inst_b": inst_b_u,
                "sa": sa_u, "sa_id": sa.id, "sb": sb_u, "sb_id": sb.id,
                "pa": pa_u, "pb": pb_u,
                "ea": ea.id, "eb": eb.id}


async def _make_syllabus(client, admin, title, grade="1", programme="piano"):
    r = await client.post("/api/v1/learning/syllabi",
                          json={"title": title, "programme_id": programme, "grade": grade},
                          headers=auth(admin))
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------------------------------------------------------------------------
# Assignment is per student; visibility follows the assignment
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_syllabus_visible_only_to_assigned_student(client, world):
    w = world
    syl_a = await _make_syllabus(client, w["admin"], "Trinity Grade 1 — Ann plan", grade="1")
    syl_b = await _make_syllabus(client, w["admin"], "Trinity Grade 2 — Bob plan", grade="2")

    r = await client.post(f"/api/v1/learning/syllabi/{syl_a}/assign",
                          json={"student_id": str(w["sa_id"]), "enrollment_id": str(w["ea"])},
                          headers=auth(w["admin"]))
    assert r.status_code == 201, r.text
    r = await client.post(f"/api/v1/learning/syllabi/{syl_b}/assign",
                          json={"student_id": str(w["sb_id"]), "enrollment_id": str(w["eb"])},
                          headers=auth(w["admin"]))
    assert r.status_code == 201

    # Ann sees only her own
    ann = await client.get("/api/v1/learning/syllabi", headers=auth(w["sa"]))
    ids_a = {x["id"] for x in ann.json()}
    assert ids_a == {syl_a}

    # Bob (same instrument) sees only his own
    bob = await client.get("/api/v1/learning/syllabi", headers=auth(w["sb"]))
    ids_b = {x["id"] for x in bob.json()}
    assert ids_b == {syl_b}

    # admin sees both
    adm = await client.get("/api/v1/learning/syllabi", headers=auth(w["admin"]))
    assert {x["id"] for x in adm.json()} == {syl_a, syl_b}


@pytest.mark.asyncio
async def test_parents_see_only_linked_children(client, world):
    w = world
    syl = await _make_syllabus(client, w["admin"], "Family-shared? No.")
    await client.post(f"/api/v1/learning/syllabi/{syl}/assign",
                      json={"student_id": str(w["sa_id"]), "enrollment_id": str(w["ea"])},
                      headers=auth(w["admin"]))

    pa = await client.get("/api/v1/learning/syllabi", headers=auth(w["pa"]))
    assert {x["id"] for x in pa.json()} == {syl}
    pb = await client.get("/api/v1/learning/syllabi", headers=auth(w["pb"]))
    assert pb.json() == []


@pytest.mark.asyncio
async def test_instructors_see_only_their_students_syllabi(client, world):
    w = world
    syl = await _make_syllabus(client, w["admin"], "Ann pathway")
    await client.post(f"/api/v1/learning/syllabi/{syl}/assign",
                      json={"student_id": str(w["sa_id"]), "enrollment_id": str(w["ea"])},
                      headers=auth(w["admin"]))

    ta = await client.get("/api/v1/learning/syllabi", headers=auth(w["inst_a"]))
    assert {x["id"] for x in ta.json()} == {syl}
    tb = await client.get("/api/v1/learning/syllabi", headers=auth(w["inst_b"]))
    assert tb.json() == []


# ---------------------------------------------------------------------------
# No API bypass
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_api_cannot_bypass_visibility(client, world):
    w = world
    syl = await _make_syllabus(client, w["admin"], "Secret pathway")
    item = await client.post(f"/api/v1/learning/syllabi/{syl}/items",
                             json={"title": "Scale 1", "item_type": "topic"},
                             headers=auth(w["admin"]))
    item_id = item.json()["id"]

    await client.post(f"/api/v1/learning/syllabi/{syl}/assign",
                      json={"student_id": str(w["sa_id"]), "enrollment_id": str(w["ea"])},
                      headers=auth(w["admin"]))

    # Bob cannot read Ann's progress even with her ids
    r = await client.get(f"/api/v1/learning/syllabus-progress?student_id={w['sa_id']}",
                         headers=auth(w["sb"]))
    assert r.status_code == 403

    # Bob's unassigned instructor cannot write Ann's progress
    r2 = await client.post(
        f"/api/v1/learning/syllabus-progress/{item_id}?student_id={w['sa_id']}&enrollment_id={w['ea']}",
        json={"status": "completed", "faculty_notes": "should not happen"},
        headers=auth(w["inst_b"]))
    assert r2.status_code == 403

    # non-admin cannot create or assign syllabi
    r3 = await client.post("/api/v1/learning/syllabi",
                           json={"title": "Rogue", "programme_id": "piano"},
                           headers=auth(w["inst_a"]))
    assert r3.status_code == 403
    r4 = await client.post(f"/api/v1/learning/syllabi/{syl}/assign",
                           json={"student_id": str(w["sb_id"]), "enrollment_id": str(w["eb"])},
                           headers=auth(w["inst_a"]))
    assert r4.status_code == 403


# ---------------------------------------------------------------------------
# Archiving removes visibility; reassignment is safe
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_archive_assignment_removes_visibility(client, world):
    w = world
    syl = await _make_syllabus(client, w["admin"], "Temporary pathway")
    a = await client.post(f"/api/v1/learning/syllabi/{syl}/assign",
                          json={"student_id": str(w["sa_id"]), "enrollment_id": str(w["ea"])},
                          headers=auth(w["admin"]))
    aid = a.json()["id"]

    before = await client.get("/api/v1/learning/syllabi", headers=auth(w["sa"]))
    assert len(before.json()) == 1

    arch = await client.patch(f"/api/v1/learning/syllabi/{syl}/assignments/{aid}",
                              json={"status": "archived"}, headers=auth(w["admin"]))
    assert arch.status_code == 200 and arch.json()["status"] == "archived"

    after = await client.get("/api/v1/learning/syllabi", headers=auth(w["sa"]))
    assert after.json() == []

    # reactivating restores it (same assignment record, history kept)
    rea = await client.post(f"/api/v1/learning/syllabi/{syl}/assign",
                            json={"student_id": str(w["sa_id"]), "enrollment_id": str(w["ea"])},
                            headers=auth(w["admin"]))
    assert rea.status_code == 201 and rea.json()["reactivated"] is True
    again = await client.get("/api/v1/learning/syllabi", headers=auth(w["sa"]))
    assert len(again.json()) == 1

    # duplicate active assignment is refused
    dup = await client.post(f"/api/v1/learning/syllabi/{syl}/assign",
                            json={"student_id": str(w["sa_id"]), "enrollment_id": str(w["ea"])},
                            headers=auth(w["admin"]))
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_two_students_same_instrument_different_syllabi(client, world):
    w = world
    grade1 = await _make_syllabus(client, w["admin"], "Piano Grade 1", grade="1")
    grade3 = await _make_syllabus(client, w["admin"], "Piano Grade 3", grade="3")
    await client.post(f"/api/v1/learning/syllabi/{grade1}/assign",
                      json={"student_id": str(w["sa_id"]), "enrollment_id": str(w["ea"])},
                      headers=auth(w["admin"]))
    await client.post(f"/api/v1/learning/syllabi/{grade3}/assign",
                      json={"student_id": str(w["sb_id"]), "enrollment_id": str(w["eb"])},
                      headers=auth(w["admin"]))

    ann = await client.get("/api/v1/learning/syllabi?programme_id=piano", headers=auth(w["sa"]))
    assert [x["grade"] for x in ann.json()] == ["1"]
    bob = await client.get("/api/v1/learning/syllabi?programme_id=piano", headers=auth(w["sb"]))
    assert [x["grade"] for x in bob.json()] == ["3"]
