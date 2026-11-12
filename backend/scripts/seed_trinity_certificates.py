#!/usr/bin/env python3
"""Seed the verified Trinity/RSL certificates into the student Hall of Fame.

The certificate images ship with the frontend (they are what families see
and download in the preview build); this script copies the same files into
the authorised upload store and records one verified achievement per
certificate, including the awarding body's own verify-original link.

Records (all genuine, all already verified by the academy):

    Siri Hosangadi   Trinity Initial Electronic Keyboard — Distinction  2026-01-16
    Siri Hosangadi   Trinity Grade 1 Electronic Keyboard — Distinction  2026-11-01
    Raina Singh      Trinity Initial Electronic Keyboard — Distinction  2026-11-01
    Sana Muttalli    Trinity Initial Electronic Keyboard — Distinction  2026-02-01
    Prakhyaat Verma  Rockschool Ukulele Entry Level — Distinction      2026-08-20

Idempotent: an achievement is never duplicated — reruns fill in anything
missing (certificate file, verify link) and leave the rest untouched.

Usage:
    cd backend
    python scripts/seed_trinity_certificates.py --dry-run
    python scripts/seed_trinity_certificates.py --apply
"""
import argparse
import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.achievement import Achievement
from app.models.student import Student
from app.services.files import upload_root

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CERT_ASSET_DIR = REPO_ROOT / "frontend" / "assets" / "certificates"

RECORDS = [
    {
        "student": "Siri Hosangadi",
        "title": "Trinity Grade 1 Electronic Keyboard — Distinction",
        "category": "exam",
        "awarding_body": "Trinity College London",
        "programme_id": "electronic_keyboard",
        "grade_level": "Grade 1",
        "result": "Distinction",
        "achieved_on": date(2026, 11, 1),
        "description": (
            "Level 1 Award in Graded Examination in Music Performance — Electronic Keyboard. "
            "Exam held 1 November 2026 at Bangalore-Music (Centre no. 287); performance uploaded "
            "2 November 2026 (12:28 IST); results published 5 November 2026 (19:21 IST); "
            "certificate issued 7 November 2026 and delivered 8 November 2026 at 01:31 IST."
        ),
        "verify_url": (
            "https://certificates.trinitycollege.com/6d9bc910-a6c1-4159-a67d-37bff94e1de3"
            "?key=4bc7a2078c10966ace91e8f8b155b7ec5aa48b0ed34103e85a7aefcaff5bd308#acc.hy29aDEr"
        ),
        "asset": "trinity-keyboard-grade1-siri-hosangadi.png",
    },
    {
        "student": "Siri Hosangadi",
        "title": "Trinity Initial Electronic Keyboard — Distinction",
        "category": "exam",
        "awarding_body": "Trinity College London",
        "programme_id": "electronic_keyboard",
        "grade_level": "Initial",
        "result": "Distinction",
        "achieved_on": date(2026, 1, 16),
        "description": (
            "Entry Level Award in Graded Examination in Music Performance (Entry 3) — Electronic Keyboard. "
            "Exam held 16 January 2026 with the performance uploaded the same day (11:06 GMT); "
            "results published 5 February 2026 (14:27 GMT); certificate issued 7 February 2026 at 20:00 GMT."
        ),
        "verify_url": (
            "https://certificates.trinitycollege.com/1ea95d81-e3ec-4b94-9d0d-7bc9e5a51df2"
            "?key=c2670931e0d25af6bcdcb6841859ec3d398549857c91316783db74917fffbdf7#acc.TLBrXDhb"
        ),
        "asset": "trinity-keyboard-initial-siri-hosangadi.png",
    },
    {
        "student": "Raina Singh",
        "title": "Trinity Initial Electronic Keyboard — Distinction",
        "category": "exam",
        "awarding_body": "Trinity College London",
        "programme_id": "electronic_keyboard",
        "grade_level": "Initial",
        "result": "Distinction",
        "achieved_on": date(2026, 11, 1),
        "description": (
            "Entry Level Award in Graded Examination in Music Performance (Entry 3) — Electronic Keyboard. "
            "Exam held 1 November 2026 at Bangalore-Music (Centre no. 287) with the performance uploaded "
            "2 November 2026 (12:28 IST); results published 5 November 2026 (19:21 IST); certificate "
            "issued 7 November 2026 and delivered 8 November 2026 at 01:31 IST."
        ),
        "verify_url": (
            "https://certificates.trinitycollege.com/94290130-59f5-4809-beca-5f4ec50edb32"
            "?key=b7b8978d78191135504ef9e6fab91321a657d43fbe12d33864302000972a9b30#acc.BHO9dorb"
        ),
        "asset": "trinity-keyboard-initial-raina-singh.png",
    },
    {
        "student": "Sana Muttalli",
        "title": "Trinity Initial Electronic Keyboard — Distinction",
        "category": "exam",
        "awarding_body": "Trinity College London",
        "programme_id": "electronic_keyboard",
        "grade_level": "Initial",
        "result": "Distinction",
        "achieved_on": date(2026, 2, 1),
        "description": (
            "Entry Level Award in Graded Examination in Music Performance (Entry 3) — Electronic Keyboard. "
            "Exam held 1 February 2026 at Bangalore-Music (Centre no. 287) with the performance uploaded "
            "2 February 2026 (06:18 GMT); results published 12 February 2026 (13:17 GMT); certificate "
            "issued 14 February 2026 (20:11 GMT)."
        ),
        "verify_url": (
            "https://certificates.trinitycollege.com/f63c3625-88d3-45a5-b6f6-f8ebcc506166"
            "?key=f4845474eb44c3871fce3a3e6f30a3c51c7007306c6123cc5082f255fe71b41d#acc.bADeE15X"
        ),
        "asset": "trinity-keyboard-initial-sana-muttalli.png",
    },
    {
        "student": "Prakhyaat Verma",
        "title": "Rockschool Ukulele Entry Level — Distinction",
        "category": "exam",
        "awarding_body": "Rockschool (RSL Awards)",
        "programme_id": "ukulele",
        "grade_level": "Entry Level",
        "result": "Distinction",
        "achieved_on": date(2026, 8, 20),
        "description": (
            "RSL Entry Level Award in Performance (Entry 3) — Ukulele, presented by "
            "Chanakya Shukla / ChankArts Music Academy on 20 August 2026. Total credits: 4."
        ),
        "verify_url": None,   # RSL share link not supplied — never invented
        "asset": "rsl-ukulele-distinction-prakhyaat-verma.png",
    },
    {
        "student": "Rhyah Kansara",
        "title": "Trinity Grade 1 Piano — Level 1 Award",
        "category": "exam",
        "awarding_body": "Trinity College London",
        "programme_id": "piano",
        "grade_level": "Grade 1",
        # The certificate (and Trinity's own verification page) states no
        # result classification — record exactly what the award says.
        "result": "Grade 1 Awarded",
        "achieved_on": date(2026, 11, 1),
        "description": (
            "Awarded Grade 1 in Piano at just seven years old — Level 1 Award in Graded "
            "Examination in Music Performance. Exam held 1 November 2026 at Bangalore-Music "
            "(Centre no. 287); results published 9 November 2026 at 19:36 IST; certificate "
            "issued 11 November 2026 and delivered 12 November 2026 at 01:34 IST. An "
            "extraordinary first grade, and only the beginning of her music journey."
        ),
        "verify_url": (
            "https://certificates.trinitycollege.com/e948931d-0545-4367-b464-b8a212a42010"
            "?key=a968468faac4f1d281f3e51c608f46dbc014447b2f17617055ba590ad50a9642#acc.nk2JchDV"
        ),
        "asset": "trinity-piano-grade1-rhyah-kansara.jpg",
    },
]

SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
)


def read_asset(name: str) -> dict:
    """Load a certificate image, detecting its real type from magic bytes."""
    path = CERT_ASSET_DIR / name
    if not path.is_file():
        raise SystemExit(f"Missing certificate asset: {path}")
    data = path.read_bytes()
    for magic, content_type, ext in SIGNATURES:
        if data.startswith(magic):
            return {"data": data, "content_type": content_type, "ext": ext}
    raise SystemExit(f"Unsupported image type (refusing to store): {path}")


def store_asset(uploads: Path, rec: dict, assets: dict) -> tuple:
    """Copy the certificate into the authorised upload store.

    Returns (stored_name, original_filename, content_type).
    """
    asset = assets[rec["asset"]]
    stored_name = f"{uuid.uuid4().hex}{asset['ext']}"
    (uploads / stored_name).write_bytes(asset["data"])
    filename = f"{rec['awarding_body']} - {rec['student']} - {rec['grade_level']}{asset['ext']}"
    return stored_name, filename, asset["content_type"]


async def run(apply: bool) -> None:
    assets = {rec["asset"]: read_asset(rec["asset"]) for rec in RECORDS}
    uploads = upload_root() / "achievements"
    if apply:
        uploads.mkdir(parents=True, exist_ok=True)

    created = updated = skipped = 0

    async with AsyncSessionLocal() as db:
        for rec in RECORDS:
            student = (await db.execute(
                select(Student).where(
                    Student.first_name.ilike(rec["student"].split()[0]),
                    Student.last_name.ilike(" ".join(rec["student"].split()[1:])),
                )
            )).scalars().first()

            if student is None:
                print(f"  ! student not found: {rec['student']}  ({rec['title']})")
                skipped += 1
                continue

            existing = (await db.execute(
                select(Achievement).where(
                    Achievement.student_id == student.id,
                    Achievement.title == rec["title"],
                )
            )).scalars().first()

            if existing is None:
                print(f"  + CREATE  {rec['student']}: {rec['title']}")
                if not apply:
                    created += 1
                    continue
                stored_name, filename, content_type = store_asset(uploads, rec, assets)
                db.add(Achievement(
                    student_id=student.id,
                    title=rec["title"],
                    category=rec["category"],
                    awarding_body=rec["awarding_body"],
                    programme_id=rec["programme_id"],
                    grade_level=rec["grade_level"],
                    result=rec["result"],
                    achieved_on=rec["achieved_on"],
                    description=rec["description"],
                    verify_url=rec["verify_url"],
                    cert_stored_name=stored_name,
                    cert_filename=filename,
                    cert_content_type=content_type,
                    is_verified=True,
                    is_archived=False,
                ))
                created += 1
                continue

            # already present: fill in anything that is missing, never duplicate
            changed = []
            if existing.verify_url != rec["verify_url"] and rec["verify_url"]:
                existing.verify_url = rec["verify_url"]
                changed.append("verify link")
            if not existing.cert_stored_name:
                stored_name, filename, content_type = store_asset(uploads, rec, assets)
                existing.cert_stored_name = stored_name
                existing.cert_filename = filename
                existing.cert_content_type = content_type
                changed.append("certificate file")
            if not existing.is_verified:
                existing.is_verified = True
                changed.append("verification")
            if changed:
                print(f"  ~ UPDATE  {rec['student']}: {rec['title']} ({', '.join(changed)})")
                updated += 1
            else:
                print(f"  = KEEP    {rec['student']}: {rec['title']}")
                skipped += 1

        if apply:
            await db.commit()

    mode = "applied" if apply else "dry-run (no changes written)"
    print(f"\n{mode}: {created} created, {updated} updated, {skipped} already present")
    if not apply:
        print("Re-run with --apply to write these records.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--dry-run", action="store_true", help="report only (default)")
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply))


if __name__ == "__main__":
    main()
