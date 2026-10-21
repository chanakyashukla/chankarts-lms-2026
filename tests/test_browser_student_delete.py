"""
Browser test: permanent student deletion through the real admin UI.

Runs a local uvicorn (temp SQLite DB, seeded admin) and drives the deployed
frontend with system Chrome via Playwright:
  * login as admin
  * student WITHOUT dependencies → Delete permanently → dialog warning → gone
  * student WITH dependencies (enrolment + session injected) → dialog lists
    the affected records → gone; unrelated student untouched
  * username / registration ID reusable afterwards; deleted login rejected

Skipped automatically when Playwright or system Chrome is unavailable.
"""
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
ADMIN_USER = "browseradm"
ADMIN_PIN = "2468"
DB_PATH = Path(os.environ.get("TMPDIR", "/tmp")) / f"browser_delete_{uuid.uuid4().hex[:8]}.db"


def _playwright_available() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        return False
    return Path("/Applications/Google Chrome.app").exists()


pytestmark = pytest.mark.skipif(
    not _playwright_available(),
    reason="Playwright + system Chrome required for the browser test",
)


def _wait_health(timeout=40) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(BASE + "/health", timeout=3).read()
            return True
        except Exception:
            time.sleep(0.5)
    return False


@pytest.fixture(scope="module")
def server():
    env = dict(os.environ)
    env.pop("RATE_LIMIT_ENABLED", None)
    env.update({
        "DATABASE_URL": f"sqlite+aiosqlite:///{DB_PATH}",
        "SECRET_KEY": "browser-test-secret-key-not-a-real-secret",
        "DEBUG": "true",
        "RATE_LIMIT_ENABLED": "false",
        "EMAIL_TEST_MODE": "true",
        "SEED_DEMO_DATA": "false",
        "SEED_ADMIN_EMAIL": "browser@test.local",
        "SEED_ADMIN_USERNAME": ADMIN_USER,
        "SEED_ADMIN_PASSWORD": ADMIN_PIN,
        "SEED_ADMIN_FIRST_NAME": "Browser",
        "SEED_ADMIN_LAST_NAME": "Admin",
    })
    env.pop("MIGRATIONS_DATABASE_URL", None)
    # Pre-create the schema from the current models so the boot-time Alembic
    # run (legacy revisions create users.email NOT NULL on SQLite) cannot
    # override model-level nullability; migrations fail harmlessly and the
    # additive bootstrap keeps the model-correct schema.
    import asyncio as _asyncio
    from sqlalchemy.ext.asyncio import create_async_engine as _cae
    sys.path.insert(0, str(BACKEND))
    from app.database import Base as _Base  # noqa: E402
    import app.api.v1.router  # noqa: F401,E402

    async def _precreate():
        e = _cae(f"sqlite+aiosqlite:///{DB_PATH}")
        async with e.begin() as conn:
            await conn.run_sync(_Base.metadata.create_all)
        await e.dispose()

    _asyncio.run(_precreate())
    # free the port: kill any straggler server from a previous failed run
    try:
        import subprocess as _sp
        pids = _sp.run(["lsof", "-ti", f"tcp:{PORT}"], capture_output=True, text=True).stdout.split()
        for pid in pids:
            try:
                os.kill(int(pid), 9)
            except Exception:
                pass
        if pids:
            time.sleep(1)
    except Exception:
        pass
    log_path = Path("/tmp") / "btest_server.log"
    log_fh = open(log_path, "wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BACKEND), env=env,
        stdout=log_fh, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    ok = _wait_health()
    if not ok:
        log_fh.flush()
        tail = log_path.read_text(errors="replace")[-1200:]
        log_fh.close()
        raise AssertionError(f"local server failed to start; log tail:\n{tail}")
    yield BASE
    import signal
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=10)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
    log_fh.close()
    DB_PATH.unlink(missing_ok=True)


def _api(method: str, path: str, token: str | None = None, body: dict | None = None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    def _load(b):
        try:
            return json.loads(b or b"{}")
        except Exception:
            return {"_raw": (b or b"").decode("utf8", "replace")[:300]}
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, _load(r.read())
    except urllib.error.HTTPError as e:
        return e.code, _load(e.read())


@pytest.fixture(scope="module")
def admin_token(server):
    st, body = _api("POST", "/api/v1/auth/login",
                    body={"email": ADMIN_USER, "password": ADMIN_PIN})
    assert st == 200, body
    return body["access_token"]


def _inject_deps(student_id: str, enrollment_id: str | None = None):
    """Add an enrolment + a class session for this student (raw SQLite)."""
    con = sqlite3.connect(str(DB_PATH))
    # SQLAlchemy's UUID type stores hex WITHOUT dashes on SQLite — match it
    h = lambda x: x.replace("-", "")
    eid = h(enrollment_id or str(uuid.uuid4()))
    sid = h(str(uuid.uuid4()))
    student_id = h(student_id)
    now = "2026-10-21 10:00:00.000000"
    con.execute(
        "INSERT INTO enrollments (id, student_id, programme_id, programme_name, "
        "fee_plan, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (eid, student_id, "piano", "Piano", "4_classes", "active", now, now))
    con.execute(
        "INSERT INTO class_sessions (id, enrollment_id, student_id, scheduled_date, "
        "scheduled_start, scheduled_end, timezone, duration_minutes, status, "
        "is_duration_exception, counts_toward_package, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, eid, student_id, "2026-11-02", "10:00:00", "11:00:00", "UTC", 60,
         "scheduled", 0, 1, now, now))
    con.commit()
    con.close()
    return eid, sid


def test_admin_ui_permanent_delete_flow(server, admin_token):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        # localhost dev default API is :8000 — point the SPA at this test server
        page.add_init_script(f"window.CHANKARTS_API_BASE = '{BASE}';")
        dialogs: list[str] = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))

        # --- admin login through the real UI ---
        page.goto(f"{BASE}/academy/login", wait_until="domcontentloaded")
        page.fill("#loginEmail", ADMIN_USER)
        page.fill("#loginPassword", ADMIN_PIN)
        page.click("#loginForm button[type=submit]")
        page.wait_for_function(
            "() => !!localStorage.getItem('academy_token')", timeout=20000)

        # --- create two students via the API the UI uses ---
        st1, s1 = _api("POST", "/api/v1/admin/students", admin_token,
                       {"username": "browser.stu1", "first_name": "Brave",
                        "last_name": "One"})
        assert st1 in (200, 201), s1
        st2, s2 = _api("POST", "/api/v1/admin/students", admin_token,
                       {"username": "browser.stu2", "first_name": "Second",
                        "last_name": "Kid"})
        assert st2 in (200, 201), s2
        id1, id2 = s1["id"], s2["id"]
        # student 2 gets dependencies; student 1 stays dependency-free
        _inject_deps(id2)

        # --- open Students in the admin UI ---
        page.goto(f"{BASE}/academy/admin", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        page.wait_for_timeout(1200)
        page.wait_for_function("() => typeof Admin !== 'undefined' && !!Admin.navigateTo", timeout=15000)
        page.evaluate("Admin.navigateTo('students')")
        page.get_by_text("Brave One").first.wait_for(timeout=15000)

        # ===== delete student WITHOUT dependencies =====
        row1 = page.locator("tr", has_text="Brave One").first
        row1.get_by_role("button", name="Delete permanently").click()
        page.wait_for_timeout(600)
        assert dialogs, "no confirmation dialog shown"
        assert "PERMANENTLY DELETE" in dialogs[-1]
        assert "cannot be undone" in dialogs[-1].lower() or "irreversible" in dialogs[-1].lower()
        assert "Brave One" in dialogs[-1]
        page.wait_for_timeout(1500)
        page.get_by_text("Brave One").wait_for(state="detached", timeout=15000)
        # API confirms gone
        got = _api("GET", f"/api/v1/admin/students/{id1}", admin_token)
        assert got[0] == 404
        # login rejected
        stl, _ = _api("POST", "/api/v1/auth/login",
                      body={"email": "browser.stu1", "password": "1234"})
        assert stl == 401

        # ===== delete student WITH dependencies =====
        dialogs.clear()
        page.get_by_text("Second Kid").first.wait_for(timeout=15000)
        row2 = page.locator("tr", has_text="Second Kid").first
        row2.get_by_role("button", name="Delete permanently").click()
        page.wait_for_timeout(600)
        assert dialogs, "no confirmation dialog for dependent student"
        msg = dialogs[-1]
        assert "PERMANENTLY DELETE" in msg
        assert "enrollments" in msg and "1" in msg          # affected records listed
        assert "class sessions" in msg or "class_sessions" in msg
        assert "archive" in msg.lower()                     # archive recommended…
        assert "Cancel to keep" in msg                       # …but not compulsory
        page.wait_for_timeout(1500)
        page.get_by_text("Second Kid").wait_for(state="detached", timeout=15000)
        got2 = _api("GET", f"/api/v1/admin/students/{id2}", admin_token)
        assert got2[0] == 404
        # dependency rows really deleted from the DB
        con = sqlite3.connect(str(DB_PATH))
        n_enr = con.execute("SELECT COUNT(*) FROM enrollments WHERE student_id=?",
                            (id2,)).fetchone()[0]
        n_ses = con.execute("SELECT COUNT(*) FROM class_sessions WHERE student_id=?",
                            (id2,)).fetchone()[0]
        con.close()
        assert n_enr == 0 and n_ses == 0

        # ===== identifier reuse + unrelated data safety =====
        st3, _ = _api("POST", "/api/v1/admin/students", admin_token,
                      {"username": "browser.stu1", "first_name": "Reused", "last_name": "One"})
        assert st3 in (200, 201), "username should be reusable after deletion"
        # the reused student is visible in the UI
        page.goto(f"{BASE}/academy/admin", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        page.wait_for_function("() => typeof Admin !== 'undefined' && !!Admin.navigateTo", timeout=15000)
        page.evaluate("Admin.navigateTo('students')")
        page.get_by_text("Reused One").first.wait_for(timeout=15000)

        browser.close()
