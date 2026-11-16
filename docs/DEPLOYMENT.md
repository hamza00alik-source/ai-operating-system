# Deployment guide (Enzonic Python hosting)

This guide prepares the existing FastAPI starter for a small always-on Python host. It does not imply that a server has been provisioned.

## Hosting profile inspected

The Enzonic panel's final review screen showed a Free plan with 512 MB RAM, 1 CPU core, 1 GB storage, and the label "Always on". The provider states that free capacity is subject to availability and is limited to one free bot/app or Minecraft server per account. Recheck the terms in the panel before deployment.

## Repository settings

- Runtime: Python 3.11 (supported by this project; use a newer runtime only after CI verifies it).
- Main file: `main.py`.
- Install dependencies from `requirements.txt`.
- Bind to `0.0.0.0` and the port supplied by the host (`PORT`, default 8000).

## Required environment variables

Set these as private environment variables in the hosting panel. Never put real values in GitHub.

| Variable | Value |
|---|---|
| `AI_OS_ENV` | `production` |
| `AI_OS_API_KEY` | A long, randomly generated secret; keep it private |
| `AI_OS_DATABASE_URL` | `sqlite:////absolute/path/on/persistent-storage/ai_os.db` |
| `VIDEO_WORKER_TOKEN` | A unique random secret for the LongCat worker only; optional until that worker is deployed |
| `VIDEO_CINECODE_WORKER_TOKEN` | A different unique random secret for the Cinecode worker only; optional until a sandboxed Cinecode worker is deployed |
| `PUBLIC_API_BASE_URL` | Public HTTPS API origin; required only when workers upload MP4 artifacts |
| `VIDEO_ARTIFACT_DIR` | `/data/video_artifacts` on the persistent Railway volume; required for durable MP4/report storage |
| `VIDEO_ARTIFACT_STORAGE_LIMIT_BYTES` | `419430400` (400 MiB aggregate cap; API also preserves at least 64 MiB free) |
| `PUBLIC_API_BASE_URL` | `https://aios-api-production-e878.up.railway.app` for the current AIOS Railway production service; use the actual HTTPS API origin if it changes |

The current AIOS Railway production service has a persistent 500 MB volume mounted at `/data`; use `/data/video_artifacts` for private MP4s and production-report sidecars. The API enforces a 400 MiB aggregate artifact cap and a 64 MiB free-space reserve so video uploads cannot silently fill the entire volume. The volume is shared with the app's persistent data, so keep the cap and database backup/retention policy under review.

The database path above is a template, not a confirmed Enzonic mount path. Replace it with the actual persistent writable directory documented or displayed by Enzonic. Do not deploy with SQLite on an ephemeral working directory if records must survive restarts/redeploys.

The application refuses to start outside development if `AI_OS_API_KEY` is missing. All task and approval endpoints require the `X-API-Key` header; `/health` remains public. Use HTTPS for all requests.

## Initial smoke tests

After deployment, verify:

1. `GET /health` returns HTTP 200.
2. `GET /tasks` without `X-API-Key` returns HTTP 401.
3. `GET /tasks` with the correct `X-API-Key` returns HTTP 200.
4. Create a test task and approval, then verify they remain after an app restart.
5. Confirm logs contain no secrets.

Do not connect WooCommerce, social accounts, payment credentials, or autonomous publishing until authentication, persistence, backups, and audit logging have been verified.

## Resource limitations

512 MB RAM and one CPU core are suitable only for the lightweight API and small jobs. Do not host large language models or multiple heavy agent processes on this server. Call external model APIs only after separately configuring a provider and its secret, with spending controls.
