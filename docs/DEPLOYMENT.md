# OpenCompany deployment guide

This guide describes how to deploy the **clean-room OpenCompany runtime** from the
`clean-room-rebuild` branch or a reviewed descendant. It does not authorize or
perform a production cutover. The existing `main` application and current
Vercel/Railway routing remain separate until the replacement passes release
checks and a rollback rehearsal.

## Runtime and persistent storage

- Runtime: Python 3.11+ (the container image uses Python 3.12).
- Build: repository `Dockerfile`.
- Start command: `python main.py` (the Dockerfile uses this command).
- Bind address: `0.0.0.0`; port: hosting platform's `PORT` or 8000.
- Attach a persistent Railway volume at `/data`.
- Set `OPENCOMPANY_DATABASE_PATH=/data/opencompany_core.sqlite3`.
- The container runs as non-root UID/GID 10001. The mounted volume must be
  writable by that identity.

Do not use an ephemeral filesystem for the SQLite database. Do not run a
second standalone worker process: `worker_main.py` is deliberately disabled
because it cannot establish the same owner-authorized provider test gate as
the API process. Workers run inside the API service.

## Required private environment variables

Set these in the hosting provider's secret/environment settings. Never commit
real values or paste them into GitHub issues or pull requests.

| Variable | Requirement |
|---|---|
| `OPENCOMPANY_OWNER_API_KEY` | Long, randomly generated owner bootstrap/API key |
| `OPENCOMPANY_SECRET_ENCRYPTION_KEY` | Separate, stable random secret of at least 32 characters; required to read/write encrypted provider credentials |
| `OPENCOMPANY_COOKIE_SECURE` | `true` behind HTTPS |
| `OPENCOMPANY_DATABASE_PATH` | `/data/opencompany_core.sqlite3` on the persistent volume |

Back up `OPENCOMPANY_SECRET_ENCRYPTION_KEY` securely. It is independent of
the owner login key. If it is lost or rotated, provider credentials already
stored in SQLite cannot be decrypted and must be entered again. The database
backup and encryption key should be stored separately with restricted access.

## Optional integrations and worker controls

- UnoRouter can be configured through the owner dashboard. The selected model
  must end in `:free`; paid fallback is disabled and the gateway uses a zero
  request budget. A successful owner-authorized live inference test is
  required before workers can start.
- If provider credentials are supplied by environment instead of the owner
  dashboard, use `OPENCOMPANY_UNOROUTER_API_KEY`,
  `OPENCOMPANY_UNOROUTER_FREE_MODEL` (must end in `:free`), and
  `OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true`.
- Set `OPENCOMPANY_WORKER_AUTOSTART=true` only if the owner wants the worker
  fleet to start automatically after a successful provider test in the
  running API process. A process restart clears the in-memory verification
  timestamp; the owner must test the provider again before the fleet can
  resume. With autostart disabled, start workers from the owner console after
  the provider test.
- API Anything is optional. Configure
  `OPENCOMPANY_API_ANYTHING_BASE_URL` and
  `OPENCOMPANY_API_ANYTHING_TOKEN`. External endpoints must use HTTPS.
  Clear-text HTTP is accepted only for loopback development or Railway's
  `.railway.internal` private service DNS. Only read-only tier-one calls are
  exposed.
- GitHub code evolution is optional and restricted to isolated draft pull
  requests. The application does not merge or deploy generated changes.

A `:free` model identifier and a zero-dollar provider response are safeguards,
not a guarantee about a provider's billing terms. Confirm current UnoRouter
pricing/terms and monitor the provider account. Do not configure paid models or
enable any paid fallback.

## Initial staging smoke tests

After a staging deployment, verify all of the following before considering
production replacement:

1. `GET /health` returns HTTP 200.
2. `GET /ready` returns HTTP 200 and reports storage as ready.
3. `GET /owner` serves the owner console with no-store and restrictive CSP
   headers.
4. Operational endpoints such as `GET /work-items` reject unauthenticated
   requests.
5. Owner login creates an HttpOnly, Secure, SameSite=Strict session cookie;
   invalid logins are rate-limited and mutating browser requests require CSRF
   protection and same-origin validation.
6. The owner can save, test, and remove provider credentials without any
   credential appearing in status responses or logs.
7. A test work item is queued only after owner admission, executed with a
   confirmed zero-cost provider, and its deliverable and usage record persist.
8. Worker shutdown/restart, database backup, restore to a separate staging
   database, and rollback have been rehearsed.
9. Container runs as non-root and the mounted database volume remains writable
   after a redeploy.

## Release and routing boundary

- Do not change production Vercel rewrites or the existing Railway service
  until the new OpenCompany API has its own verified staging endpoint.
- The current `vercel.json` rewrite still points to the legacy Railway API.
  This is intentional; changing it before staging verification would break
  the live application.
- Do not apply migrations to, switch, or overwrite the production database as
  part of this rebuild.
- Do not merge the rebuild PR or deploy it to production while required CI
  checks are failing or unavailable.
- Production cutover requires an owner-approved maintenance window, a
  verified database backup, a tested restore/rollback path, and smoke tests
  against the exact candidate commit.
