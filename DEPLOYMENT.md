# ChankArts Academy LMS — Deployment Guide

The LMS is a FastAPI backend (`backend/`) + static SPA frontend (`frontend/`).
This guide targets **free-tier or self-hostable** infrastructure. No hosting
account setup is performed by the code — everything below is a manual step
for the account owner.

---

## 1. Architecture

```
Browser ──► Static frontend (Cloudflare Pages / GitHub Pages / any static host)
                 │  /api/*  (reverse proxy or CORS)
                 ▼
            FastAPI backend (Render / Railway / any Docker host)
                 │
                 ▼
            PostgreSQL (Neon / Supabase / Railway / self-hosted)
```

The frontend calls `/api/v1/*` **same-origin by default**. Two supported ways
to connect it to the backend:

- **A. Reverse proxy (recommended):** the static host proxies `/api/*` to the
  backend. On Cloudflare Pages, uncomment the `/api/*` rule in
  `frontend/_redirects` and set your API host. No CORS changes needed.
- **B. Direct origin:** set `window.CHANKARTS_API_BASE = "https://api.example.com"`
  in `frontend/index.html` (before the other scripts) and add that frontend
  origin to the backend's `ALLOWED_ORIGINS` env var.

> GitHub Pages cannot proxy `/api/*`, so option B is required there (or use
> Cloudflare Pages / a custom domain). This is why the GitHub Pages preview
> cannot authenticate on its own.

---

## 2. Backend deployment (free tier examples)

Any service that can run a Docker container or `uvicorn` works.

### Option 1 — Render.com (free web service) + Neon (free PostgreSQL)
1. Create a free **Neon** PostgreSQL database → copy the connection string.
2. Create a **Render Web Service** from this repository:
   - Dockerfile detected automatically (`Dockerfile` at repo root).
   - Or native Python: build `pip install -r backend/requirements.txt`,
     start `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Set environment variables (see §4).
4. Health check path: `/health`.
5. First boot runs Alembic migrations + an additive schema bootstrap
   (`app/db_bootstrap.py`) that aligns a fresh database with the models, then
   seeds the administrator from `SEED_ADMIN_*` (once).

### Option 2 — Railway (usage-based free credit) or any Docker host
`railway.json` and `Dockerfile` are ready. `docker-compose.yml` provides a
local PostgreSQL for self-hosting.

### Option 3 — Self-hosted (VPS, NAS, home server)
```bash
docker build -t chankarts-lms .
docker run -d -p 8000:8000 --env-file .env chankarts-lms
```
Put a TLS reverse proxy (Caddy/Nginx/Cloudflare Tunnel) in front.

---

## 3. Frontend deployment

- **Cloudflare Pages** (current production frontend): connect the frontend
  repository, then edit `_redirects` per §1-A. `index.html`/`js/` are the
  published files; SPA fallback is already configured.
- **GitHub Pages:** works for UI preview only; use §1-B for the API.

The login deep-link, PIN setup screens and all dashboards work once `/api/v1`
resolves to the deployed backend.

---

## 4. Environment variables (`backend/.env` — never committed)

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+asyncpg://user:pass@host/db` (Neon/Railway/Supabase provide this) |
| `SECRET_KEY` | yes | long random string; JWT signing |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_USERNAME` / `SEED_ADMIN_PASSWORD` | yes | initial administrator, seeded once |
| `ALLOWED_ORIGINS` | optional | extra CORS origins, comma separated (defaults cover chankarts.com, academy.chankarts.com, localhost) |
| `FRONTEND_URL` | optional | used in emails/links |
| `RAZORPAY_MODE` / `RAZORPAY_KEY_ID` / `RAZORPAY_KEY_SECRET` / `RAZORPAY_WEBHOOK_SECRET` | optional | leave `RAZORPAY_MODE=disabled` to run without payments |
| `WEB3FORMS_ACCESS_KEY` / `EMAIL_TEST_MODE` | optional | email sending |
| `UPLOAD_DIR` / `MAX_UPLOAD_MB` | optional | attachment storage |

See `backend/.env.example` for the full template.

---

## 5. What runs automatically on first start

1. `alembic upgrade head` — base schema (entrypoint / startup).
2. `app/db_bootstrap.sync_schema` — additive, idempotent: creates any missing
   tables/columns the models declare (development-era tables are covered here),
   relaxes legacy NOT NULL constraints. **Never destructive.**
3. Administrator seeding from `SEED_ADMIN_*` (skipped if it exists).

Data persistence: all state lives in the PostgreSQL database (students,
sessions, fee ledger, payments, reports). Attachments live under `UPLOAD_DIR` —
mount a persistent volume for that directory on hosts with ephemeral disks.

---

## 6. Verification checklist (after deployment)

1. `GET https://<api-host>/health` → 200
2. `GET https://<frontend>/` → app loads
3. Login with the seeded administrator → dashboard renders
4. First login with a temporary PIN forces a PIN change; the new PIN works
5. Create a student, record a fee charge and a manual payment → both appear in
   the student portal after admin confirmation (manual payment confirmation)
6. Restart the service → all records still present (persistence)

---

## 7. Free-tier notes

- **Render free web service** spins down when idle (first request is slow) —
  fine for a school portal; a paid instance removes the cold start.
- **Neon/Supabase free PostgreSQL** is persistent and sufficient for this data
  volume. Avoid hosts where the database lives on an ephemeral filesystem
  without a persistent disk (plain Render free *disk* is ephemeral).
- Backups: use the provider's automated backups; before schema work take a
  manual dump (`pg_dump`).
