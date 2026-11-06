"""
Student-portal notifications: every admin/faculty action that gives or updates
something for a student (assignments, materials, syllabus, submissions, exams,
milestones, remarks, reports, resources, achievements) produces a de-duplicated,
correctly-scoped in-app notification — and staff-only records stay silent.
"""
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DATABASE_URL = "sqlite+aiosqlite:///./test_student_notifications.db"
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
from app.models.enrollment import Enrollment
from app.models.notification import Notification
from app.models.guardian import GuardianAccount
from app.models.learning import Assignment, Submission
from app.models.session import ClassSession, SessionStatus


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
async def world():
    async with TestSessionLocal() as s:
        admin = User(id=uuid.uuid4(), username="notifadmin", hashed_password=get_password_hash("0000"),
                     role=UserRole.ADMIN, is_active=True, must_change_pin=False)
        s.add(admin)
        await s.flush()
        s.add(Admin(id=uuid.uuid4(), user_id=admin.id, first_name="Noti", last_name="Admin",
                    admin_level="super_admin", is_active=True))
        iu = User(id=uuid.uuid4(), username="notifins", hashed_password=get_password_hash("1234"),
                  role=UserRole.INSTRUCTOR, is_active=True, must_change_pin=False)
        s.add(iu); await s.flush()
        ins = Instructor(id=uuid.uuid4(), user_id=iu.id, first_name="Noti", last_name="Ins", is_active=True)
        s.add(ins)
        stu_ids = {}
        for uname, name in (("notifstu1", "Notify"), ("notifstu2", "Other")):
            su = User(id=uuid.uuid4(), username=uname, hashed_password=get_password_hash("1234"),
                      role=UserRole.STUDENT, is_active=True, must_change_pin=False)
            s.add(su); await s.flush()
            st = Student(id=uuid.uuid4(), user_id=su.id,
                         cma_registration_id=f"CMA-2026-{uuid.uuid4().hex[:5].upper()}",
                         portal_slug=f"p{uuid.uuid4().hex[:8]}", first_name=name, last_name="Stu",
                         status="active")
            s.add(st); await s.flush()
            e = Enrollment(id=uuid.uuid4(), student_id=st.id, programme_id="piano",
                           programme_name="Piano", instructor_id=ins.id,
                           fee_plan="4_classes", fee_amount=4500, status="active")
            s.add(e)
            stu_ids[uname] = {"user": su.id, "student": st.id, "enrollment": e.id}
        # parent linked to student1
        pu = User(id=uuid.uuid4(), username="notifparent", hashed_password=get_password_hash("1234"),
                  role=UserRole.PARENT, is_active=True, must_change_pin=False)
        s.add(pu); await s.flush()
        s.add(GuardianAccount(id=uuid.uuid4(), user_id=pu.id, student_id=stu_ids["notifstu1"]["student"]))
        await s.commit()
        return {"admin": admin.id, "instructor_user": iu.id, "instructor": ins.id,
                "parent_user": pu.id, **{k: v for k, v in stu_ids.items()}}


def tok(user_id, role) -> dict:
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user_id), 'role': role}, expires_delta=timedelta(minutes=30))}"}


async def _portal_notifs(client, user_id):
    r = await client.get("/api/v1/portal/notifications", headers=tok(user_id, "student"))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_assignment_created_notifies_student_from_admin_and_faculty(client, world):
    h = tok(world["admin"], "admin")
    r = await client.post("/api/v1/learning/assignments", json={
        "enrollment_id": str(world["notifstu1"]["enrollment"]),
        "title": "Scales homework", "assigned_date": "2026-11-01"}, headers=h)
    assert r.status_code == 201, r.text
    aid = r.json().get("id") or r.json().get("assignment_id")

    n1 = await _portal_notifs(client, world["notifstu1"]["user"])
    mine = [n for n in n1 if n["type"] == "assignment.created"]
    assert len(mine) == 1
    assert "Scales homework" in mine[0]["title"]
    assert mine[0]["read"] is False

    # the OTHER student sees nothing (scoping)
    n2 = await _portal_notifs(client, world["notifstu2"]["user"])
    assert all(n["type"] != "assignment.created" for n in n2)

    # faculty-created assignment also notifies (faculty side)
    ih = tok(world["instructor_user"], "instructor")
    r = await client.post("/api/v1/learning/assignments", json={
        "enrollment_id": str(world["notifstu1"]["enrollment"]),
        "title": "Faculty task", "assigned_date": "2026-11-02"}, headers=ih)
    assert r.status_code == 201, r.text
    n1 = await _portal_notifs(client, world["notifstu1"]["user"])
    assert len([n for n in n1 if n["type"] == "assignment.created"]) == 2

    # mark-read flow
    r = await client.post("/api/v1/portal/notifications/read", json={},
                          headers=tok(world["notifstu1"]["user"], "student"))
    assert r.status_code == 200 and r.json()["marked_read"] >= 2
    n1 = await _portal_notifs(client, world["notifstu1"]["user"])
    assert all(n["read"] for n in n1)


@pytest.mark.asyncio
async def test_material_assign_notifies_each_student_and_update_notifies_once(client, world):
    h = tok(world["admin"], "admin")
    # create material
    # create_material accepts multipart form fields (not JSON)
    r = await client.post("/api/v1/learning/materials",
                          data={"title": "Fingerbusters", "category": "technique",
                                "level": "beginner",
                                "link_url": "https://example.com/fingerbusters"}, headers=h)
    assert r.status_code in (200, 201), r.text
    mid = r.json()["id"]
    # assign to BOTH students — each must get their own notification
    for key in ("notifstu1", "notifstu2"):
        r = await client.post(f"/api/v1/learning/materials/{mid}/assign",
                              json={"student_id": str(world[key]["student"]),
                                    "enrollment_id": str(world[key]["enrollment"])}, headers=h)
        assert r.status_code == 201, r.text
    for key in ("notifstu1", "notifstu2"):
        n = await _portal_notifs(client, world[key]["user"])
        assert len([x for x in n if x["type"] == "material.assigned"]) == 1, key
    # update material → assigned students notified (versioned dedupe)
    r = await client.patch(f"/api/v1/learning/materials/{mid}", json={"description": "updated"}, headers=h)
    assert r.status_code == 200
    for key in ("notifstu1", "notifstu2"):
        n = await _portal_notifs(client, world[key]["user"])
        assert len([x for x in n if x["type"] == "material.updated"]) == 1, key


@pytest.mark.asyncio
async def test_syllabus_assign_notifies_student(client, world):
    h = tok(world["admin"], "admin")
    r = await client.post("/api/v1/learning/syllabi", json={
        "title": "Trinity Grade 1", "instrument": "piano", "programme_id": "piano"}, headers=h)
    assert r.status_code in (200, 201), r.text
    syl_id = r.json().get("id")
    r = await client.post(f"/api/v1/learning/syllabi/{syl_id}/assign", json={
        "student_id": str(world["notifstu1"]["student"]),
        "enrollment_id": str(world["notifstu1"]["enrollment"])}, headers=h)
    assert r.status_code in (200, 201), r.text
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert any(x["type"] == "syllabus.assigned" for x in n)


@pytest.mark.asyncio
async def test_submission_review_notifies_student(client, world):
    h = tok(world["admin"], "admin")
    r = await client.post("/api/v1/learning/assignments", json={
        "enrollment_id": str(world["notifstu1"]["enrollment"]),
        "title": "Review me", "assigned_date": "2026-11-01"}, headers=h)
    aid = r.json().get("id") or r.json().get("assignment_id")
    async with TestSessionLocal() as s:
        sub = Submission(assignment_id=uuid.UUID(aid),
                         student_id=uuid.UUID(str(world["notifstu1"]["student"])),
                         status="submitted", notes="my attempt")
        s.add(sub); await s.commit()
        sub_id = str(sub.id)
    r = await client.post(f"/api/v1/learning/submissions/{sub_id}/review",
                          json={"feedback": "Nice work — keep practicing scales.",
                                "status": "reviewed"}, headers=h)
    assert r.status_code == 200, r.text
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    rev = [x for x in n if x["type"] == "assignment.reviewed"]
    assert len(rev) == 1 and "reviewed" in rev[0]["title"].lower()


@pytest.mark.asyncio
async def test_exam_create_and_result_notifies(client, world):
    h = tok(world["admin"], "admin")
    r = await client.post("/api/v1/learning/exams", json={
        "student_id": str(world["notifstu1"]["student"]),
        "enrollment_id": str(world["notifstu1"]["enrollment"]),
        "board": "trinity", "instrument": "piano", "submission_deadline": "2026-12-15"}, headers=h)
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert any(x["type"] == "exam.added" for x in n)
    # unrelated edit → no new result notification
    r = await client.patch(f"/api/v1/learning/exams/{eid}", json={"notes": "extra note"}, headers=h)
    assert r.status_code == 200
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert not any(x["type"] == "exam.result" for x in n)
    # result change → notified
    r = await client.patch(f"/api/v1/learning/exams/{eid}", json={"result": "pass"}, headers=h)
    assert r.status_code == 200
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    res = [x for x in n if x["type"] == "exam.result"]
    assert len(res) == 1 and "pass" in res[0]["title"]
    # same result again → no duplicate (dedupe by result value)
    r = await client.patch(f"/api/v1/learning/exams/{eid}", json={"result": "pass", "notes": "again"}, headers=h)
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert len([x for x in n if x["type"] == "exam.result"]) == 1


@pytest.mark.asyncio
async def test_milestone_notifies_student(client, world):
    h = tok(world["admin"], "admin")
    r = await client.post("/api/v1/learning/milestones", json={
        "student_id": str(world["notifstu1"]["student"]),
        "title": "First stage performance"}, headers=h)
    assert r.status_code in (200, 201), r.text
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert any(x["type"] == "milestone.added" for x in n)


@pytest.mark.asyncio
async def test_remark_visibility_drives_notifications(client, world):
    h = tok(world["admin"], "admin")
    # staff_only → nobody notified (privacy)
    r = await client.post("/api/v1/remarks", json={
        "student_id": str(world["notifstu1"]["student"]),
        "visibility": "staff_only", "body": "internal note"}, headers=h)
    assert r.status_code in (200, 201), r.text
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert not any(x["type"] == "remark.added" for x in n)
    # student_visible → student notified
    r = await client.post("/api/v1/remarks", json={
        "student_id": str(world["notifstu1"]["student"]),
        "visibility": "student_visible", "body": "Great progress this month"}, headers=h)
    assert r.status_code in (200, 201)
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert any(x["type"] == "remark.added" for x in n)
    # parent_visible → guardian notified, student NOT notified again for it
    before = len([x for x in n if x["type"] == "remark.added"])
    r = await client.post("/api/v1/remarks", json={
        "student_id": str(world["notifstu1"]["student"]),
        "visibility": "parent_visible", "body": "please ensure practice time"}, headers=h)
    assert r.status_code in (200, 201)
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert len([x for x in n if x["type"] == "remark.added"]) == before   # student not notified for parent-only
    pn = await client.get("/api/v1/portal/notifications", headers=tok(world["parent_user"], "parent"))
    assert pn.status_code == 200 and any(x["type"] == "remark.added" for x in pn.json())


@pytest.mark.asyncio
async def test_report_publish_notifies(client, world):
    h = tok(world["admin"], "admin")
    r = await client.post("/api/v1/learning/reports", json={
        "student_id": str(world["notifstu1"]["student"]),
        "enrollment_id": str(world["notifstu1"]["enrollment"]),
        "report_month": "2026-10"}, headers=h)
    assert r.status_code in (200, 201), r.text
    rid = r.json().get("id") or r.json().get("report_id")
    r = await client.post(f"/api/v1/learning/reports/{rid}/publish", headers=h)
    assert r.status_code == 200, r.text
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert any(x["type"] == "report.published" for x in n)


@pytest.mark.asyncio
async def test_recommendations_notify_matching_audience(client, world):
    h = tok(world["admin"], "admin")
    # targeted: only stu1
    r = await client.post("/api/v1/learning/recommendations", json={
        "resource_type": "online_link", "name": "Targeted link",
        "external_url": "https://example.com/x", "visibility_scope": "students",
        "target_student_ids": [str(world["notifstu1"]["student"])]}, headers=h)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    n1 = await _portal_notifs(client, world["notifstu1"]["user"])
    n2 = await _portal_notifs(client, world["notifstu2"]["user"])
    assert any(x["type"] == "resource.added" for x in n1)
    assert not any(x["type"] == "resource.added" for x in n2)
    # catalogue-wide: BOTH students notified
    r = await client.post("/api/v1/learning/recommendations", json={
        "resource_type": "book", "name": "Scale mastery book"}, headers=h)
    assert r.status_code == 201
    n1 = await _portal_notifs(client, world["notifstu1"]["user"])
    n2 = await _portal_notifs(client, world["notifstu2"]["user"])
    assert len([x for x in n1 if x["type"] == "resource.added"]) == 2   # targeted + catalogue-wide
    assert len([x for x in n2 if x["type"] == "resource.added"]) == 1   # catalogue-wide only
    # update → resource.updated for audience
    r = await client.patch(f"/api/v1/learning/recommendations/{rid}",
                           json={"name": "Targeted link v2"}, headers=h)
    assert r.status_code == 200
    n1 = await _portal_notifs(client, world["notifstu1"]["user"])
    assert any(x["type"] == "resource.updated" for x in n1)
    n2 = await _portal_notifs(client, world["notifstu2"]["user"])
    assert not any(x["type"] == "resource.updated" for x in n2)   # not in audience


@pytest.mark.asyncio
async def test_achievement_publish_notifies_once(client, world):
    h = tok(world["admin"], "admin")
    r = await client.post("/api/v1/admin/achievements", json={
        "student_id": str(world["notifstu1"]["student"]),
        "title": "Winter recital star", "category": "recital"}, headers=h)
    assert r.status_code in (200, 201), r.text
    aid = r.json()["id"]
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert not any(x["type"] == "achievement.published" for x in n)   # unverified yet
    r = await client.patch(f"/api/v1/admin/achievements/{aid}", json={"is_verified": True}, headers=h)
    assert r.status_code == 200, r.text
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert len([x for x in n if x["type"] == "achievement.published"]) == 1
    # re-verify / re-edit → no duplicate publish notification
    r = await client.patch(f"/api/v1/admin/achievements/{aid}", json={"is_verified": True, "result": "distinction"}, headers=h)
    n = await _portal_notifs(client, world["notifstu1"]["user"])
    assert len([x for x in n if x["type"] == "achievement.published"]) == 1


@pytest.mark.asyncio
async def test_scoped_and_unread_endpoints(client, world):
    h = tok(world["admin"], "admin")
    await client.post("/api/v1/learning/milestones", json={
        "student_id": str(world["notifstu2"]["student"]), "title": "Other kid milestone"}, headers=h)
    # unread-only filter
    unread = await client.get("/api/v1/portal/notifications?unread_only=true",
                              headers=tok(world["notifstu2"]["user"], "student"))
    assert unread.status_code == 200
    assert all(x["read"] is False for x in unread.json())
    # isolation: student2 never sees student1's items
    n2 = await _portal_notifs(client, world["notifstu2"]["user"])
    assert all("Scales" not in (x.get("title") or "") for x in n2)
    # read-state persists via service
    await client.post("/api/v1/portal/notifications/read", json={},
                      headers=tok(world["notifstu2"]["user"], "student"))
    unread = await client.get("/api/v1/portal/notifications?unread_only=true",
                              headers=tok(world["notifstu2"]["user"], "student"))
    assert unread.json() == []
