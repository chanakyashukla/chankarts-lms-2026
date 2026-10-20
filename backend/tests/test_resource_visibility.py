"""
Targeted resource visibility.

- Global resources reach everyone.
- Student-specific resources reach only their targets (never the whole academy).
- Programme- and level-specific resources reach only the matching audience.
- Parents inherit visibility only for their linked children.
- Instructors see only resources relevant to their students.
- Visibility is enforced in API responses, not just hidden in the UI.
"""
from datetime import timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_resource_visibility.db"
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
    """Piano student (beginner, instructor I, parent P) + guitar student."""
    async with TestSessionLocal() as db:
        admin_u = User(username="rvadmin", email="rvadmin@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.ADMIN)
        db.add(admin_u)
        await db.flush()
        db.add(Admin(user_id=admin_u.id, first_name="RV", last_name="Admin",
                     admin_level="super_admin", is_active=True))

        inst_u = User(username="rvinst", email="rvinst@t.local",
                      hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(inst_u)
        await db.flush()
        inst = Instructor(user_id=inst_u.id, first_name="RV", last_name="Faculty",
                          specializations="piano", is_active=True)
        db.add(inst)

        other_u = User(username="rvother", email="rvother@t.local",
                       hashed_password=get_password_hash("x"), role=UserRole.INSTRUCTOR)
        db.add(other_u)
        await db.flush()
        other = Instructor(user_id=other_u.id, first_name="Un", last_name="Related",
                           specializations="guitar", is_active=True)
        db.add(other)

        piano_u = User(username="CMA-9601", hashed_password=get_password_hash("9601"),
                       role=UserRole.STUDENT)
        guitar_u = User(username="CMA-9602", hashed_password=get_password_hash("9602"),
                        role=UserRole.STUDENT)
        db.add_all([piano_u, guitar_u])
        await db.flush()
        piano = Student(user_id=piano_u.id, cma_registration_id="CMA-2026-9601",
                        first_name="Pia", last_name="No", status="active",
                        skill_level="beginner")
        guitar = Student(user_id=guitar_u.id, cma_registration_id="CMA-2026-9602",
                         first_name="Gui", last_name="Tar", status="active",
                         skill_level="advanced")
        db.add_all([piano, guitar])
        await db.flush()
        ep = Enrollment(student_id=piano.id, programme_id="piano", programme_name="Piano",
                        instructor_id=inst.id, fee_plan="4_classes", fee_amount=4500,
                        status="active")
        eg = Enrollment(student_id=guitar.id, programme_id="guitar", programme_name="Guitar",
                        instructor_id=other.id, fee_plan="4_classes", fee_amount=4500,
                        status="active")
        db.add_all([ep, eg])

        parent_u = User(username="rvparent", email="rvparent@t.local",
                        hashed_password=get_password_hash("x"), role=UserRole.PARENT)
        db.add(parent_u)
        await db.flush()
        db.add(GuardianAccount(user_id=parent_u.id, student_id=piano.id, relationship="mother"))
        await db.commit()
        return {"admin": admin_u, "instructor": inst_u, "other_inst": other_u,
                "piano": piano_u, "piano_id": piano.id,
                "guitar": guitar_u, "guitar_id": guitar.id,
                "parent": parent_u}


async def _mk_material(client, admin, **form):
    data = {"title": "Resource", "category": "repertoire",
            "link_url": "https://chankarts.example/resource"}
    data.update(form)
    r = await client.post("/api/v1/learning/materials", data=data, headers=auth(admin))
    assert r.status_code == 201, r.text
    return r.json()


async def _mk_rec(client, admin, **json):
    payload = {"resource_type": "accessory", "name": "Capo"}
    payload.update(json)
    r = await client.post("/api/v1/learning/recommendations", json=payload, headers=auth(admin))
    assert r.status_code == 201, r.text
    return r.json()


def _ids(rows):
    return {x["id"] for x in rows}


# ---------------------------------------------------------------------------
# Global vs student-specific
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_global_reaches_everyone_student_specific_only_target(client, world):
    w = world
    glob = await _mk_material(client, w["admin"], title="Global songbook", visibility_scope="all")
    spec = await _mk_material(client, w["admin"], title="Only for Pia",
                              visibility_scope="students",
                              target_student_ids=str(w["piano_id"]))

    pia = await client.get("/api/v1/learning/materials", headers=auth(w["piano"]))
    assert _ids(pia.json()) == {glob["id"], spec["id"]}

    gui = await client.get("/api/v1/learning/materials", headers=auth(w["guitar"]))
    assert _ids(gui.json()) == {glob["id"]}

    # API response itself omits the other student's resource — not just the UI
    assert spec["id"] not in _ids(gui.json())
    assert all(x["title"] != "Only for Pia" for x in gui.json())


# ---------------------------------------------------------------------------
# Programme + level targeting
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_programme_and_level_targeting(client, world):
    w = world
    piano_mat = await _mk_material(client, w["admin"], title="Piano scale chart",
                                   programme_id="piano", visibility_scope="programme")
    beginner_mat = await _mk_material(client, w["admin"], title="Beginner piano pieces",
                                      programme_id="piano", level="beginner",
                                      visibility_scope="programme")
    guitar_mat = await _mk_material(client, w["admin"], title="Capo exercise sheet",
                                    programme_id="guitar", visibility_scope="programme")

    pia = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["piano"]))).json())
    gui = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["guitar"]))).json())
    assert piano_mat["id"] in pia and guitar_mat["id"] not in pia
    # level AND-filter: pia is beginner -> sees both; guitar student is advanced
    assert beginner_mat["id"] in pia
    assert guitar_mat["id"] in gui and piano_mat["id"] not in gui

    # admin sees everything
    adm = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["admin"]))).json())
    assert {piano_mat["id"], beginner_mat["id"], guitar_mat["id"]} <= adm


# ---------------------------------------------------------------------------
# Parents and instructors inherit only their own scope
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_parent_and_instructor_scoped(client, world):
    w = world
    spec = await _mk_material(client, w["admin"], title="Family note",
                              visibility_scope="students",
                              target_student_ids=str(w["piano_id"]))
    g_only = await _mk_material(client, w["admin"], title="Guitar family note",
                                visibility_scope="students",
                                target_student_ids=str(w["guitar_id"]))

    par = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["parent"]))).json())
    assert spec["id"] in par and g_only["id"] not in par

    teach = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["instructor"]))).json())
    assert spec["id"] in teach and g_only["id"] not in teach

    unrel = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["other_inst"]))).json())
    assert g_only["id"] in unrel and spec["id"] not in unrel


# ---------------------------------------------------------------------------
# Recommendations follow the same rules (the capo example)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recommendation_targeting(client, world):
    w = world
    capo = await _mk_rec(client, w["admin"], name="Capo recommendation",
                         programme_id="guitar", visibility_scope="programme")
    book = await _mk_rec(client, w["admin"], name="Practice notebook",
                         visibility_scope="all")
    personal = await _mk_rec(client, w["admin"], name="Pia's special strings",
                             visibility_scope="students",
                             target_student_ids=[str(w["piano_id"])])

    pia = _ids((await client.get("/api/v1/learning/recommendations", headers=auth(w["piano"]))).json())
    gui = _ids((await client.get("/api/v1/learning/recommendations", headers=auth(w["guitar"]))).json())
    assert book["id"] in pia and book["id"] in gui
    assert capo["id"] not in pia and capo["id"] in gui       # capo stays guitar-only
    assert personal["id"] in pia and personal["id"] not in gui


# ---------------------------------------------------------------------------
# Editing visibility changes the audience
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_visibility_patch_changes_audience(client, world):
    w = world
    mat = await _mk_material(client, w["admin"], title="Movable resource",
                             visibility_scope="students",
                             target_student_ids=str(w["piano_id"]))
    before = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["guitar"]))).json())
    assert mat["id"] not in before

    # widen to global explicitly
    await client.patch(f"/api/v1/learning/materials/{mat['id']}",
                       json={"visibility_scope": "all"}, headers=auth(w["admin"]))
    after = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["guitar"]))).json())
    assert mat["id"] in after

    # ... and back to a single student
    await client.patch(f"/api/v1/learning/materials/{mat['id']}",
                       json={"visibility_scope": "students",
                             "target_student_ids": [str(w["guitar_id"])]},
                       headers=auth(w["admin"]))
    pia_now = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["piano"]))).json())
    gui_now = _ids((await client.get("/api/v1/learning/materials", headers=auth(w["guitar"]))).json())
    assert mat["id"] not in pia_now and mat["id"] in gui_now


# ---------------------------------------------------------------------------
# Invalid scope rejected; students cannot create resources
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scope_validation_and_permissions(client, world):
    w = world
    bad = await client.post("/api/v1/learning/materials",
                            data={"title": "X", "category": "repertoire",
                                  "visibility_scope": "everyone-ish"},
                            headers=auth(w["admin"]))
    assert bad.status_code == 400

    denied = await client.post("/api/v1/learning/materials",
                               data={"title": "X", "category": "repertoire"},
                               headers=auth(w["piano"]))
    assert denied.status_code == 403

    denied2 = await client.post("/api/v1/learning/recommendations",
                                json={"resource_type": "book", "name": "Rogue"},
                                headers=auth(w["piano"]))
    assert denied2.status_code == 403
