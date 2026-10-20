"""
Same-origin frontend routing (Render single-service deployment).

Verifies: /academy/* serves the real static SPA with deep-link fallback,
unknown API endpoints keep JSON 404s (frontend HTML is never returned for
/api/*), path traversal cannot escape the frontend directory, and the
preview adapter stays inactive when a real backend serves the origin.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_endpoint(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_academy_root_redirects_to_slash(client):
    r = await client.get("/academy")
    assert r.status_code in (302, 307, 308)
    assert r.headers["location"] == "/academy/"


@pytest.mark.asyncio
async def test_academy_index_serves_spa(client):
    r = await client.get("/academy/")
    assert r.status_code == 200
    assert "ChankArts Music Academy" in r.text
    assert "preview-api.js" in r.text  # first script — real-backend gate present


@pytest.mark.asyncio
async def test_static_assets_served(client):
    for asset in ("/academy/js/app.js", "/academy/css/styles.css", "/academy/js/preview-api.js"):
        r = await client.get(asset)
        assert r.status_code == 200, asset
        assert "text/" in r.headers.get("content-type", "") or "javascript" in r.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_spa_deep_link_fallback(client):
    for route in ("/academy/login", "/academy/portal/dashboard", "/academy/admin"):
        r = await client.get(route)
        assert r.status_code == 200, route
        assert "ChankArts Music Academy" in r.text, route


@pytest.mark.asyncio
async def test_unknown_api_endpoint_stays_json_404(client):
    r = await client.get("/api/v1/definitely-not-a-route")
    assert r.status_code == 404
    assert "text/html" not in r.headers.get("content-type", "")
    assert r.json()["detail"] == "Not Found"


@pytest.mark.asyncio
async def test_unknown_root_path_is_404_not_spa(client):
    r = await client.get("/totally-unknown-page")
    assert r.status_code == 404
    assert "text/html" not in r.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_path_traversal_cannot_escape(client):
    for evil in ("/academy/%2e%2e%2f%2e%2e%2fbackend%2f.env",
                 "/academy/%2e%2e/%2e%2e/README.md",
                 "/academy/../app/main.py"):
        r = await client.get(evil)
        body = r.text
        # never leaks backend files or environment values
        assert "SECRET_KEY" not in body
        assert "DATABASE_URL=" not in body
        assert "def main" not in body


@pytest.mark.asyncio
async def test_api_and_docs_still_work_alongside_static(client):
    r = await client.get("/docs")
    assert r.status_code == 200
    # empty body -> FastAPI/pydantic 422 (no database access required),
    # proving API routes answer before any frontend fallback
    r = await client.post("/api/v1/auth/login", json={})
    assert r.status_code == 422
    assert "text/html" not in r.headers.get("content-type", "")
    assert r.json()["detail"][0]["type"] == "missing"
