"""
Same-origin frontend serving for single-service deployments (Render Free).

Serves the existing static SPA from the repository's frontend/ directory
under the preserved /academy/ base path, AFTER the API routes:

  - /academy/<file>      -> the real file (css/js/images/…)
  - /academy/<anything>  -> index.html (SPA deep-link fallback)
  - /academy, /          -> redirect to /academy/

API behaviour is untouched: unknown /api/v1/* endpoints keep FastAPI's
JSON 404 because these routes only match the /academy prefix. Paths are
resolved and confined to the frontend directory (no traversal).
"""
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

router = APIRouter()


def frontend_dir() -> Path:
    """frontend/ lives at the repository root (override with FRONTEND_DIR)."""
    override = os.environ.get("FRONTEND_DIR")
    if override:
        return Path(override).resolve()
    here = Path(__file__).resolve()          # <root>/backend/app/static_frontend.py
    for candidate in (here.parent.parent.parent / "frontend", here.parent.parent / "frontend"):
        if candidate.is_dir():
            return candidate.resolve()
    raise RuntimeError("frontend/ directory not found (set FRONTEND_DIR)")


def _resolve_file(relative: str) -> Optional[Path]:
    root = frontend_dir()
    target = (root / relative.lstrip("/")).resolve()
    # path-traversal guard: resolved path must stay inside the frontend dir
    if target == root or root in target.parents:
        if target.is_file():
            return target
    return None


@router.get("/academy")
async def academy_root():
    return RedirectResponse("/academy/")


@router.get("/academy/")
async def academy_index():
    path = frontend_dir() / "index.html"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(path)


@router.get("/academy/{full_path:path}")
async def academy_spa(full_path: str):
    """Real asset if it exists, otherwise the SPA shell (deep links)."""
    if full_path:
        found = _resolve_file(full_path)
        if found is not None:
            return FileResponse(found)
    # SPA fallback for client-side routes (login, portal/…, admin…)
    index = frontend_dir() / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    return FileResponse(index)
