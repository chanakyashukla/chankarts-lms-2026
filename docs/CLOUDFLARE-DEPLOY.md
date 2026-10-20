# Cloudflare Production Deployment — ChankArts LMS 2026

Production architecture (selected):

```
Browser ──► Cloudflare Worker (chankarts-lms)
              ├─ /api/*, /health, /docs ──► Cloudflare Container (root Dockerfile,
              │                             FastAPI, one instance "main")
              │                                ├─► Neon PostgreSQL (all business data)
              │                                └─► R2 bucket (uploads, FUSE mount)
              └─ everything else ──► Workers Static Assets (frontend/, SPA fallback)
```

The GitHub Pages demo (`chanakyashukla.github.io/chankarts-lms-2026`) is
unchanged and remains a labelled, browser-local demo. The production domain
can never activate the demo adapter (`frontend/js/preview-api.js` gate:
preview mode is permitted only on `*.github.io` and localhost).

---

## 0. Cost and plan requirements (read first)

**Cloudflare Containers require the Workers Paid plan ($5 USD/month base).**
Included usage on that plan (per Cloudflare's published pricing):

| Resource | Included / month | Overage |
|---|---|---|
| Memory | 25 GiB-hours | $0.0000025 / GiB-second |
| vCPU | 375 vCPU-minutes | $0.000020 / vCPU-second |
| Disk | 200 GB-hours | $0.00000007 / GB-second |
| Egress (NA & EU) | 1 TB | $0.025 / GB |

Billed only while a container is **awake** (it sleeps after the 5-minute
idle timeout configured in `worker/src/index.js`, so bursty school usage
stays near zero). This deployment uses **one** `lite` instance
(256 MiB RAM / 1/16 vCPU / 2 GB disk) — chosen against a measured ~10 MB
idle footprint of the application; revisit `instance: "lite"` in
`worker/src/index.js` only if load testing shows memory pressure.

Neon Free PostgreSQL and Cloudflare R2 free allowance (10 GB storage) are
sufficient for an academy (a few MB holds thousands of students).

---

## 1. One-time account setup (owner actions — do not skip)

1. **Workers Paid plan**: Cloudflare dashboard → Workers & Pages → Plan →
   upgrade to Workers Paid ($5/month). Required for Containers.
2. **Neon database**: create a free project at neon.tech → copy the pooled
   connection string → it becomes `DATABASE_URL`
   (`postgresql+asyncpg://USER:PASSWORD@HOST/neondb?sslmode=require`).
3. **R2 bucket**: Cloudflare dashboard → R2 → create bucket
   `chankarts-lms-uploads` → manage R2 API tokens → create a token with
   Object Read & Write scoped to that bucket → note the Access Key ID and
   Secret (they become `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`), and
   the Account ID (→ `R2_ACCOUNT_ID` in `wrangler.jsonc` vars).
4. **Cloudflare login**: `npx wrangler login` (browser approval as
   `chanakyashukla`).

## 2. Secrets (never committed)

```bash
npx wrangler secret put DATABASE_URL
npx wrangler secret put SECRET_KEY
npx wrangler secret put SEED_ADMIN_PASSWORD     # + EMAIL/USERNAME via vars or secrets
npx wrangler secret put AWS_ACCESS_KEY_ID
npx wrangler secret put AWS_SECRET_ACCESS_KEY
```

Template: `.dev.vars.example`. Also set `R2_ACCOUNT_ID` in `wrangler.jsonc`.

## 3. Deploy to staging first

```bash
npx wrangler dev          # local end-to-end with Docker (optional)
npx wrangler deploy       # staging: <name>.<account>.workers.dev
```

Run the staging verification (health, login, Party A/B shared-state test,
reschedule + payment confirmation across two browsers, redeploy persistence,
role enforcement via direct API calls) **before** attaching any custom domain.

## 4. Production domain (only after staging passes)

Attach `academy.chankarts.com` in the Workers dashboard
(Workers & Pages → chankarts-lms → Domains & Routes) **or** via DNS route
owned by the account. Do not alter `chankarts.com` or the main website.

## 5. Operations

- **Migrations**: run exactly once at application startup
  (`app/main.py` → alembic + additive `sync_schema`); the container
  entrypoint deliberately does not run them again.
- **Uploads**: mounted R2 bucket (`docker-entrypoint.sh` mounts at
  `/mnt/r2` via tigrisfs; `UPLOAD_DIR` defaults to `/mnt/r2/uploads`).
  Files survive container restarts/sleep.
- **Backups**: Neon provides automated backups; before schema work take
  `pg_dump`.
- **Health**: `GET /health` (used by the Worker's readiness check).

## 6. Why not D1 / GitHub-as-database

- The application uses async SQLAlchemy + asyncpg + Alembic + bcrypt —
  Cloudflare's Python Workers do not support that stack; the Container runs
  the existing application unmodified (no port, no rewrite).
- A GitHub repository cannot serve as a writable shared database without
  embedding an access credential in the public site (see the architecture
  analysis).
