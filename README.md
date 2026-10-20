# ChankArts LMS 2026

Learning Management System for ChankArts Music Academy — students, CMA
registration IDs, guardians, weekly schedules, class records & calendar,
fee ledger with manual reconciliation, monthly progress reports,
assignments & quizzes, and Trinity/Rockschool syllabus tracking.

## Live preview

**https://chanakyashukla.github.io/chankarts-lms-2026/**

The preview runs the complete application in the browser (GitHub Pages
serves static files only). All screens and controls are functional against a
browser-side data store — the banner at the bottom states this clearly and
the data is labelled **demo data**. Production runs the API in `backend/`
against PostgreSQL (see `docs/DEPLOYMENT.md`).

**Preview demo sign-ins** (preview only — production credentials are seeded
from environment variables):

| Role | Login | PIN |
|---|---|---|
| Admin | `admin` | `1234` |
| Instructor | `instructor1` | `2468` |
| Parent | `parent1` | `1111` |
| Student | `CMA-001` | `9001` |

## Structure

```
frontend/       Responsive SPA (student / parent / instructor / admin)
backend/        FastAPI API, models, migrations, scripts
tests/          Application workflow tests
backend/tests/  Full backend test suite
docs/           Setup, operations and deployment guides
```

## Run locally

Backend (persistent database):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # set DATABASE_URL + SECRET_KEY + SEED_ADMIN_*
uvicorn app.main:app --reload --port 8000
```

Frontend (separate terminal):

```bash
python3 dev_server.py     # serves the SPA at http://127.0.0.1:3000/
# add ?preview=1 to run fully without the backend
```

## Tests

```bash
pytest tests/ backend/tests/ -q     # 187 tests (workflows + full backend)
node --check frontend/js/app.js
node --check frontend/js/portal.js
node --check frontend/js/admin.js
node --check frontend/js/preview-api.js
```

## Deployment

See `docs/DEPLOYMENT.md`. The API is a standard Docker/uvicorn service with
PostgreSQL; the frontend is static and proxies `/api/v1` to the backend (or
uses `window.CHANKARTS_API_BASE`). **Nothing is ever faked:** payments only
update after manual admin verification or a verified Razorpay event, and
online payments stay disabled until real credentials are configured.
