"""
Safe file storage for homework and study material.

- Server-side validation using magic bytes (never trust the file extension)
- Non-guessable storage names (uuid4)
- Files live outside the web root and are only served through authorized APIs
"""
import hashlib
import os
import uuid
from pathlib import Path
from typing import Optional, Tuple

from fastapi import HTTPException, UploadFile

from app.config import get_settings

_MAGIC_CHECKS = {
    "application/pdf": lambda h: h.startswith(b"%PDF"),
    "image/jpeg": lambda h: h.startswith(b"\xff\xd8\xff"),
    "image/png": lambda h: h.startswith(b"\x89PNG\r\n\x1a\n"),
    "audio/mpeg": lambda h: h.startswith(b"ID3") or h[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
}

EXT_BY_TYPE = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "audio/mpeg": ".mp3",
}

BASE_HOMEWORK_TYPES = {"application/pdf", "image/jpeg", "image/png"}
AUDIO_TYPES = {"audio/mpeg"}


def upload_root() -> Path:
    root = Path(get_settings().UPLOAD_DIR)
    if not root.is_absolute():
        root = Path(__file__).resolve().parent.parent / root
    return root


async def save_upload(file: UploadFile, *, subdir: str, allowed_types: set[str]) -> Tuple[str, str, int, str]:
    """
    Validate and persist an upload.

    Returns (stored_name, content_type, size_bytes, sha256).
    """
    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    header = await file.read(16)
    if not header:
        raise HTTPException(status_code=400, detail="Empty file")

    content_type = None
    for declared, check in _MAGIC_CHECKS.items():
        if check(header):
            content_type = declared
            break
    if content_type is None:
        raise HTTPException(status_code=400, detail="Unsupported file type")
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"{content_type} files are not permitted here. Allowed: {', '.join(sorted(allowed_types))}",
        )

    rest = await file.read()
    data = header + rest
    size = len(data)
    if size > max_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds the {settings.MAX_UPLOAD_MB} MB limit")

    stored_name = f"{uuid.uuid4().hex}{EXT_BY_TYPE[content_type]}"
    target_dir = upload_root() / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / stored_name
    target_path.write_bytes(data)

    digest = hashlib.sha256(data).hexdigest()
    return stored_name, content_type, size, digest


def resolve_stored_file(subdir: str, stored_name: str) -> Optional[Path]:
    """Resolve a stored file, refusing path traversal."""
    if "/" in stored_name or "\\" in stored_name or ".." in stored_name:
        return None
    path = (upload_root() / subdir / stored_name).resolve()
    base = (upload_root() / subdir).resolve()
    if not str(path).startswith(str(base)):
        return None
    return path if path.is_file() else None


def safe_filename(name: Optional[str]) -> str:
    name = (name or "file").strip()
    name = os.path.basename(name)
    return name[:180] or "file"
