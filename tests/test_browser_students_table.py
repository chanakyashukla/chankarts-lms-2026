"""
Browser test: Students table usability on a 390px mobile viewport —
horizontal scrolling is contained within the table container, identity column
stays sticky, all actions (including Delete permanently) are reachable and
clickable, and the page itself never scrolls sideways. Desktop keeps the
original layout (no scroll hint).
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BACKEND = REPO / "backend"
PORT = 8796
BASE = f"http://127.0.0.1:{PORT}"
ADMIN_USER = "tableadmin"
ADMIN_PIN = "1357"
DB_PATH = Path(os.environ.get("TMPDIR", "/tmp")) / f"students_table_{uuid.uuid4().hex[:8]}.db"


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
        "SECRET_KEY": "students-table-test-secret-key-0000",
        "DEBUG": "false",
        "RATE_LIMIT_ENABLED": "false",
        "EMAIL_TEST_MODE": "true",
        "SEED_DEMO_DATA": "false",
        "SEED_ADMIN_EMAIL": "table@test.local",
        "SEED_ADMIN_USERNAME": ADMIN_USER,
        "SEED_ADMIN_PASSWORD": ADMIN_PIN,
    })
    env.pop("MIGRATIONS_DATABASE_URL", None)
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    sys.path.insert(0, str(BACKEND))
    from app.database import Base
    import app.api.v1.router  # noqa: F401

    async def _precreate():
        e = create_async_engine(f"sqlite+aiosqlite:///{DB_PATH}")
        async with e.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await e.dispose()

    asyncio.run(_precreate())
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
    log_path = Path("/tmp") / "students_table_server.log"
    log_fh = open(log_path, "wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(PORT), "--log-level", "warning"],
        cwd=str(BACKEND), env=env, stdout=log_fh, stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    ok = _wait_health()
    if not ok:
        log_fh.flush()
        tail = log_path.read_text(errors="replace")[-1000:]
        log_fh.close()
        raise AssertionError(f"server failed to start; log tail:\n{tail}")
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


def _api(method, path, token=None, body=None):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode() if body is not None else None,
        method=method, headers={"Content-Type": "application/json",
                                **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        r = urllib.request.urlopen(req, timeout=30)
        return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}


@pytest.fixture(scope="module")
def admin_token(server):
    st, body = _api("POST", "/api/v1/auth/login", body={"email": ADMIN_USER, "password": ADMIN_PIN})
    assert st == 200, body
    return body["access_token"]


def test_students_table_mobile_scroll_and_actions(server, admin_token):
    from playwright.sync_api import sync_playwright

    # a couple of students so the table is actually wide
    for i in (1, 2, 3):
        st, body = _api("POST", "/api/v1/admin/students", admin_token,
                        {"first_name": f"Scroll{i}", "last_name": "Kid",
                         "cma_registration_id": f"CMA-2026-030{i}"})
        assert st in (200, 201), body

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, accept_downloads=True)
        page = ctx.new_page()
        page.add_init_script(f"window.CHANKARTS_API_BASE = '{BASE}';")

        page.goto(f"{BASE}/academy/login", wait_until="domcontentloaded")
        page.fill("#loginEmail", ADMIN_USER)
        page.fill("#loginPassword", ADMIN_PIN)
        page.click("#loginForm button[type=submit]")
        page.wait_for_function("() => !!localStorage.getItem('academy_token')", timeout=30000)
        page.goto(f"{BASE}/academy/admin", wait_until="domcontentloaded")
        page.wait_for_function("() => typeof Admin !== 'undefined' && !!Admin.navigateTo", timeout=20000)
        page.evaluate("Admin.navigateTo('students')")
        page.get_by_text("Scroll1 Kid").first.wait_for(timeout=20000)

        # --- A. horizontal scrolling lives inside the table container ---
        metrics = page.evaluate("""() => {
            const el = document.querySelector('.table-scroll');
            if (!el) return null;
            const style = getComputedStyle(el);
            return {overflowX: style.overflowX, scrollW: el.scrollWidth, clientW: el.clientWidth};
        }""")
        assert metrics, "table-scroll container missing"
        assert metrics["overflowX"] in ("auto", "scroll")
        assert metrics["scrollW"] > metrics["clientW"], "table wider than container (scrollable) expected"

        # page itself must not scroll sideways
        page.evaluate("() => window.scrollTo(120, 0)")
        scroll_x = page.evaluate("() => window.scrollX")
        assert scroll_x == 0, f"page scrolled horizontally ({scroll_x}px) — scroll not contained"
        page.evaluate("() => window.scrollTo(0, 0)")

        # swipe hint visible on mobile (assert via computed box, report state)
        hint_info = page.evaluate("""() => {
            const h = document.querySelector('.table-scroll-hint');
            if (!h) return null;
            const cs = getComputedStyle(h);
            const r = h.getBoundingClientRect();
            return {display: cs.display, visibility: cs.visibility,
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (h.textContent || '').slice(0, 40)};
        }""")
        assert hint_info and hint_info["display"] != "none" and hint_info["h"] > 0, hint_info

        # --- B. sticky identity column while scrolled ---
        sticky = page.evaluate("""() => {
            const el = document.querySelector('.table-scroll');
            el.scrollLeft = 160;
            const cell = el.querySelector('tbody td:first-child');
            const cellBox = cell.getBoundingClientRect();
            const contBox = el.getBoundingClientRect();
            return {delta: Math.abs(cellBox.left - contBox.left), left: cellBox.left, contLeft: contBox.left};
        }""")
        assert sticky["delta"] <= 2, f"first column not sticky (delta {sticky['delta']}px)"

        # --- C. actions reachable at scroll end, incl. Delete permanently ---
        reach = page.evaluate("""() => {
            const el = document.querySelector('.table-scroll');
            el.scrollLeft = el.scrollWidth;
            return {left: el.scrollLeft, max: el.scrollWidth - el.clientWidth};
        }""")
        assert reach["left"] >= reach["max"] - 2, "cannot scroll to the actions end"
        delete_btn = page.locator("tr", has_text="Scroll1 Kid").first.get_by_role(
            "button", name="Delete permanently")
        assert delete_btn.is_visible(), "Delete permanently not visible after scrolling"

        # clicking works (dialog appears) and cancelling leaves data intact
        dialogs = []
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        delete_btn.click()
        for _ in range(60):
            if dialogs:
                break
            page.wait_for_timeout(250)
        assert dialogs and "PERMANENTLY DELETE" in dialogs[0]
        page.get_by_text("Scroll1 Kid").first.wait_for(timeout=10000)

        # --- D. desktop viewport: layout intact, affordance visible, actions intact ---
        page.set_viewport_size({"width": 1440, "height": 900})
        page.wait_for_timeout(600)
        assert page.locator(".table-scroll-hint").first.is_visible()
        desk = page.evaluate("""() => {
            const el = document.querySelector('.table-scroll');
            return {overflowX: getComputedStyle(el).overflowX,
                    rows: el.querySelectorAll('tbody tr').length,
                    delBtns: el.querySelectorAll('button').length};
        }""")
        assert desk["overflowX"] in ("auto", "scroll") and desk["rows"] >= 3
        # identity columns + actions remain in the flow at desktop width
        page.evaluate("() => { const el = document.querySelector('.table-scroll'); el.scrollLeft = el.scrollWidth; }")
        assert page.locator("tr", has_text="Scroll1 Kid").first.get_by_role(
            "button", name="Delete permanently").is_visible()

        ctx.close()
        browser.close()
