"""
Browser test: interactive onboarding & guided tours (spec §8, §9).

Real Chromium against a live local server with real student + instructor
accounts:

Student
  1. first login shows the mandatory PIN screen FIRST (no tour yet)
  2. after PIN change the welcome introduction appears (student copy only)
  3. Start → spotlight bubble with progress; Next/Back work
  4. cross-page step navigates the portal (dashboard → classes → back)
  5. refreshing mid-tour does NOT restart the tour; welcome offers Resume
     and resumes at the saved step
  6. Skip Tour persists server-side; reload does not re-show the intro
  7. Help & Support → Replay Guided Tour restarts from step 1
  8. topic tutorial opens just that step; Finish Tour persists completion
     (reload shows no welcome)
  9. mobile viewport: bubble + controls stay inside the viewport

Instructor
  10. first login → PIN change → instructor welcome copy (not student copy)
  11. instructor tour is role-specific (9 steps, no billing step) and the
      instructor Help centre lists instructor topics only
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
PORT = 8798
BASE = f"http://127.0.0.1:{PORT}"
ADMIN_USER = "touradmin"
ADMIN_PIN = "2468"
DB_PATH = Path(os.environ.get("TMPDIR", "/tmp")) / f"tour_onboarding_{uuid.uuid4().hex[:8]}.db"


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
        "SECRET_KEY": "tour-onboarding-test-secret-key-0000",
        "DEBUG": "false",
        "RATE_LIMIT_ENABLED": "false",
        "EMAIL_TEST_MODE": "true",
        "SEED_DEMO_DATA": "false",
        "SEED_ADMIN_EMAIL": "tour@test.local",
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
        pids = subprocess.run(["lsof", "-ti", f"tcp:{PORT}"], capture_output=True, text=True).stdout.split()
        for pid in pids:
            try:
                os.kill(int(pid), 9)
            except Exception:
                pass
        if pids:
            time.sleep(1)
    except Exception:
        pass
    log_path = Path("/tmp") / "tour_onboarding_server.log"
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


def _create_student(admin_token, i):
    st, body = _api("POST", "/api/v1/admin/students", admin_token, {
        "username": f"tourstu{i}",
        "first_name": f"Tour{i}",
        "last_name": "Student",
        "cma_registration_id": f"CMA-2026-77{i:02d}",
    })
    assert st in (200, 201), body
    return body  # {login_id, temp_pin, ...}


def _create_instructor(admin_token, i):
    st, body = _api("POST", "/api/v1/admin/instructors", admin_token, {
        "username": f"tourfac{i}",
        "first_name": f"Tour{i}",
        "last_name": "Faculty",
    })
    assert st in (200, 201), body
    return body  # {login_id, temp_pin, ...}


def _forced_pin_change(page, temp_pin, new_pin):
    """Complete the mandatory first-login PIN change form."""
    page.wait_for_selector("#forcedPinForm", timeout=20000)
    page.fill("#pinCurrent", temp_pin)
    page.fill("#pinNew", new_pin)
    page.fill("#pinConfirm", new_pin)
    page.click("#forcedPinForm button[type=submit]")
    # portal must mount after the change
    page.wait_for_function("() => !!document.getElementById('portalRoot')", timeout=30000)


def _start_login(page, login_id, pin):
    page.goto(f"{BASE}/academy/login", wait_until="domcontentloaded")
    page.fill("#loginEmail", login_id)
    page.fill("#loginPassword", pin)
    page.click("#loginForm button[type=submit]")


def _new_pin_different_from(temp_pin):
    return "1357" if temp_pin == "2468" else "2468"


def _norm(text):
    """Lower-case rendered text — CSS text-transform uppercases some labels."""
    return (text or "").lower()


def _wait_step(page, title, timeout=20000):
    """Wait until the bubble is VISIBLE and showing the given step title.

    The engine writes the title synchronously but keeps the bubble hidden
    until its async target resolves — so visibility must be part of the
    condition before reading text.
    """
    page.wait_for_function(
        """(expected) => {
            const b = document.querySelector('#tourRoot .tour-bubble');
            if (!b) return false;
            const t = b.querySelector('.tour-bubble__title');
            const visible = b.getBoundingClientRect().width > 0 &&
                getComputedStyle(b).visibility !== 'hidden';
            return visible && t && t.textContent === expected;
        }""",
        arg=title, timeout=timeout)


# ---------------------------------------------------------------------------
# Student lifecycle
# ---------------------------------------------------------------------------
def test_student_first_login_tour_lifecycle(server, admin_token):
    from playwright.sync_api import sync_playwright

    creds = _create_student(admin_token, 1)
    login_id, temp_pin = creds["login_id"], creds["temp_pin"]
    new_pin = _new_pin_different_from(temp_pin)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.add_init_script(f"window.CHANKARTS_API_BASE = '{BASE}';")

        # --- 1. PIN screen comes first; no tour before it ---
        _start_login(page, login_id, temp_pin)
        page.wait_for_selector("#forcedPinForm", timeout=20000)
        assert page.locator("#tourWelcomeRoot").count() == 0, "welcome must not precede the PIN change"
        assert page.locator("#tourRoot").count() == 0, "tour must not precede the PIN change"

        # --- 2. after PIN change the student welcome appears ---
        _forced_pin_change(page, temp_pin, new_pin)
        page.wait_for_selector("#tourWelcomeRoot", timeout=20000)
        welcome = page.locator("#tourWelcomeRoot")
        wtext = welcome.inner_text()
        assert "welcome to chankarts music academy!" in _norm(wtext), wtext
        assert "instructor portal" not in _norm(wtext), "student must not see instructor copy"
        assert welcome.locator('[data-welcome="start"]').is_visible()
        assert welcome.locator('[data-welcome="skip"]').is_visible()

        # --- 3. Start → bubble with progress ---
        welcome.locator('[data-welcome="start"]').click()
        _wait_step(page, "Your Learning Dashboard")
        bubble = page.locator("#tourRoot .tour-bubble")
        assert "step 1 of 10" in _norm(bubble.inner_text())
        assert "your learning dashboard" in _norm(bubble.inner_text())
        assert page.locator("#tourRoot .tour-spotlight").is_visible()
        # controls present
        for label in ("Back", "Skip Tour", "Next"):
            assert bubble.locator(f'[data-tour]', has_text=label).first.is_visible(), label
        # Back disabled on step 1
        assert bubble.locator('[data-tour="back"]').is_disabled()

        # --- 4. Next/Back + cross-page navigation ---
        bubble.locator('[data-tour="next"]').click()
        _wait_step(page, "Notifications")
        bubble.locator('[data-tour="next"]').click()
        # step 3 is the classes section — engine must navigate there
        page.wait_for_url("**/academy/portal/classes", timeout=15000)
        _wait_step(page, "Your Class Schedule")
        assert "step 3 of 10" in _norm(page.locator(".tour-bubble").inner_text())

        # Back returns to the previous step (and back to the dashboard section)
        page.locator('.tour-bubble [data-tour="back"]').click()
        page.wait_for_url(f"{BASE}/academy/portal/dashboard", timeout=15000)
        _wait_step(page, "Notifications")

        # --- 5. refresh mid-tour: tour is NOT restarted; Resume works ---
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#portalRoot", timeout=30000)
        page.wait_for_timeout(1500)  # auto-launch window
        assert page.locator("#tourRoot").count() == 0, "refresh must not restart the tour"
        page.wait_for_selector("#tourWelcomeRoot", timeout=15000)
        resume_btn = page.locator('#tourWelcomeRoot [data-welcome="start"]')
        assert "resume" in _norm(resume_btn.inner_text()), resume_btn.inner_text()
        resume_btn.click()
        _wait_step(page, "Notifications")  # last displayed step was #2
        assert "step 2 of 10" in _norm(page.locator(".tour-bubble").inner_text())

        # --- 6. Skip Tour persists server-side; no re-show on reload ---
        page.locator('.tour-bubble [data-tour="skip"]').click()
        page.wait_for_function("() => !document.getElementById('tourRoot')", timeout=10000)
        # login again to read state with a fresh token
        st, login = _api("POST", "/api/v1/auth/login", body={"email": login_id, "password": new_pin})
        assert st == 200, login
        st, ob = _api("GET", "/api/v1/onboarding", token=login["access_token"])
        assert st == 200 and ob["skipped"] is True, ob
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#portalRoot", timeout=30000)
        page.wait_for_timeout(1500)
        assert page.locator("#tourWelcomeRoot").count() == 0, "skip must prevent auto-launch"
        assert page.locator("#tourRoot").count() == 0

        # --- 7. Help & Support tutorial centre: replay + topics + written help ---
        page.evaluate("Portal.navigate('help')")
        page.wait_for_selector("#tourCentre", timeout=15000)
        centre = page.locator("#tourCentre")
        assert "getting started / guided tutorials" in _norm(centre.inner_text())
        assert centre.locator('[data-action="tour-replay"]').is_visible()
        assert centre.locator('[data-action="tour-topic"]').count() >= 5
        assert centre.locator("details.tour-faq").count() >= 3, "written help present"

        # replay restarts from the beginning even after a skip
        centre.locator('[data-action="tour-replay"]').click()
        _wait_step(page, "Your Learning Dashboard")
        assert "step 1 of 10" in _norm(page.locator(".tour-bubble").inner_text())
        # exit without finishing (Escape) — the tour navigated us to the
        # dashboard, so return to Help for the topic buttons
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.getElementById('tourRoot')", timeout=10000)
        page.evaluate("Portal.navigate('help')")
        page.wait_for_selector("#tourCentre", timeout=15000)

        # --- 8. topic tutorial runs only its own step; finish persists ---
        page.locator('[data-action="tour-topic"][data-id="schedule"]').click()
        _wait_step(page, "Your Class Schedule")
        ttext = page.locator(".tour-bubble").inner_text()
        assert "step 1 of 1" in _norm(ttext), ttext
        assert "your class schedule" in _norm(ttext)
        # wait for navigation to the classes section then finish
        page.wait_for_url("**/academy/portal/classes", timeout=15000)
        page.locator('.tour-bubble [data-tour="next"]').click()  # Finish Tour
        page.wait_for_function("() => !document.getElementById('tourRoot')", timeout=10000)

        # full tour completion persists: replay the FULL tour and finish it
        page.evaluate("Portal.navigate('help')")
        page.wait_for_selector("#tourCentre", timeout=15000)
        page.locator('[data-action="tour-replay"]').click()
        _wait_step(page, "Your Learning Dashboard")
        for _ in range(15):
            if page.locator("#tourRoot").count() == 0:
                break
            # click only once the bubble is actually visible (engine hides it
            # while resolving each step's async target); Playwright's click
            # would otherwise time out on a hidden node.
            try:
                page.wait_for_function(
                    """() => {
                        const b = document.querySelector('#tourRoot .tour-bubble');
                        return !!b && b.getBoundingClientRect().width > 0 &&
                            getComputedStyle(b).visibility !== 'hidden';
                    }""", timeout=8000)
            except Exception:
                if page.locator("#tourRoot").count() == 0:
                    break
                raise
            page.locator('.tour-bubble [data-tour="next"]').click()
            page.wait_for_timeout(400)
        page.wait_for_function("() => !document.getElementById('tourRoot')", timeout=20000)
        st, login = _api("POST", "/api/v1/auth/login", body={"email": login_id, "password": new_pin})
        st, ob = _api("GET", "/api/v1/onboarding", token=login["access_token"])
        assert ob["completed"] is True, ob
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#portalRoot", timeout=30000)
        page.wait_for_timeout(1500)
        assert page.locator("#tourWelcomeRoot").count() == 0, "completed tour never auto-launches"

        # --- 9. mobile viewport: bubble + controls inside the screen ---
        page.set_viewport_size({"width": 390, "height": 844})
        page.evaluate("Portal.navigate('help')")
        page.wait_for_selector("#tourCentre", timeout=15000)
        page.locator('[data-action="tour-replay"]').click()
        _wait_step(page, "Your Learning Dashboard")
        box = page.locator("#tourRoot .tour-bubble").bounding_box()
        assert box, "bubble has no box on mobile"
        assert box["x"] >= 0 and box["y"] >= 0, box
        assert box["x"] + box["width"] <= 390 + 1, box
        assert box["y"] + box["height"] <= 844 + 1, box
        for label in ("Back", "Skip Tour", "Next"):
            btn = page.locator('.tour-bubble [data-tour]', has_text=label).first
            assert btn.is_visible(), label
            bb = btn.bounding_box()
            assert bb and bb["height"] >= 30, f"{label} not comfortably tappable: {bb}"
        page.keyboard.press("Escape")

        browser.close()


# ---------------------------------------------------------------------------
# Instructor role-specific tour
# ---------------------------------------------------------------------------
def test_instructor_first_login_tour(server, admin_token):
    from playwright.sync_api import sync_playwright

    creds = _create_instructor(admin_token, 1)
    login_id, temp_pin = creds["login_id"], creds["temp_pin"]
    new_pin = _new_pin_different_from(temp_pin)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800})
        page = ctx.new_page()
        page.add_init_script(f"window.CHANKARTS_API_BASE = '{BASE}';")

        # --- 10. PIN change first, then INSTRUCTOR welcome copy ---
        _start_login(page, login_id, temp_pin)
        page.wait_for_selector("#forcedPinForm", timeout=20000)
        _forced_pin_change(page, temp_pin, new_pin)
        page.wait_for_selector("#tourWelcomeRoot", timeout=20000)
        wtext = page.locator("#tourWelcomeRoot").inner_text()
        assert "instructor portal" in _norm(wtext), wtext
        assert "your learning portal is your personal space" not in _norm(wtext), \
            "instructor must not see the student welcome copy"

        # --- 11. role-specific tour: 9 steps, instructor topics ---
        page.locator('#tourWelcomeRoot [data-welcome="start"]').click()
        _wait_step(page, "Instructor Dashboard")
        assert "step 1 of 9" in _norm(page.locator(".tour-bubble").inner_text())
        # walk to the mark-complete step (3rd) to confirm instructor content
        page.locator('.tour-bubble [data-tour="next"]').click()
        page.wait_for_timeout(800)
        page.locator('.tour-bubble [data-tour="next"]').click()
        _wait_step(page, "Marking a Class Completed")
        # no billing/fees step anywhere in the instructor tour
        titles = page.evaluate("() => Tours.INSTRUCTOR_STEPS.map(s => s.id)")
        assert "billing" not in titles
        assert "mark-complete" in titles
        page.keyboard.press("Escape")
        page.wait_for_function("() => !document.getElementById('tourRoot')", timeout=10000)

        # instructor Help centre: instructor topics, no student-only topics
        page.evaluate("Portal.navigate('help')")
        page.wait_for_selector("#tourCentre", timeout=15000)
        centre_text = page.locator("#tourCentre").inner_text()
        assert "how to mark classes completed" in _norm(centre_text)
        assert "how to view and pay fees" not in _norm(centre_text), \
            "instructor help must not list the student fee topic"

        # independent state: this instructor sees the intro even though the
        # student account already skipped/completed theirs (different user)
        st, login = _api("POST", "/api/v1/auth/login", body={"email": login_id, "password": new_pin})
        st, ob = _api("GET", "/api/v1/onboarding", token=login["access_token"])
        assert st == 200 and ob["shown"] is True, ob
        assert ob["skipped"] is False and ob["completed"] is False, ob

        browser.close()
