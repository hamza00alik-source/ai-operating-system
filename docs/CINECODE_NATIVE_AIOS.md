# Cinecode Studio — native AIOS integration

Cinecode is integrated into the active AIOS application branch as a separately
scoped owner-approved render queue. This is independent of the legacy
OpenCompany implementation and its PR #142.

## Owner workflow

1. Open /cinecode while signed in to the AIOS owner console.
2. Submit a film brief, Quick/Film mode, and explicit music choice (none or
   original code-generated music).
3. Review the stored brief and explicitly approve or reject it.
4. Approved work remains queued until a separately provisioned local worker
   is enabled. The API does not execute renders itself.
5. Completed MP4 and production report are private owner-only downloads.
6. Publishing, social posting, customer commitments, and paid fallbacks are
   not integrated.

## Native API

- GET /cinecode/status
- GET /cinecode/jobs
- POST /cinecode/jobs
- GET /cinecode/jobs/{id}
- POST /cinecode/jobs/{id}/approve
- POST /cinecode/jobs/{id}/reject
- POST /cinecode/jobs/{id}/cancel
- GET /cinecode/jobs/{id}/artifact
- GET /cinecode/jobs/{id}/report

All routes require the strict AIOS owner authentication dependency. The queue
stores only brief/job metadata; private output files are kept outside the
public web root. MP4s are capped at 250 MiB and are only downloadable after
the worker validates a video stream and duration with ffprobe.

## Worker isolation and explicit gates

The worker is a separate process and disabled by default. It refuses to start
unless all are true:

- AI_OS_CINECODE_EXECUTION_ENABLED=true
- AI_OS_CINECODE_BILLING_CONFIRMED=true
- CINECODE_SOURCE_DIR is a clean Git checkout at exactly
  CINECODE_SOURCE_COMMIT
- CODEX_HOME points to a dedicated Codex service identity directory

Use a separate least-privilege Codex account with a hard spend cap. Never mount
the owner's everyday Codex credentials. Codex and local agent commands may
read the service identity's auth directory; workspace-write is not a complete
security boundary. Apply host/firewall egress restrictions and do not expose
the worker container publicly. The Compose profile uses a read-only root
filesystem, drops Linux capabilities, and mounts source read-only. The
container still needs host-level network egress controls and a persistent
shared database with the AIOS API.

## Build and provision

1. Review Cinecode's upstream license and pin the exact reviewed commit.
2. Build: docker build -f Dockerfile.cinecode-worker -t aios-cinecode-worker:local .
3. Provision private/codex-home using a dedicated Codex service account and
   private/cinecode-source as a clean checkout at the pinned commit.
4. Configure the same persistent AI_OS_DATABASE_URL as the AIOS API,
   CINECODE_SOURCE_COMMIT, and a hard account spend cap.
5. Keep both execution gates false until the service identity, usage terms,
   firewall policy, and storage budget have been reviewed.
6. Start only after owner authorization:
   docker compose -f docker-compose.cinecode.yml --profile cinecode up -d --build

The worker writes private artifacts to the named Docker volume
cinecode-artifacts. For production, use a durable encrypted volume with
access restricted to the AIOS API and worker. Do not use ephemeral container
storage.

## Current limitations

- The worker renders a single brief at a time and has a one-hour render limit.
- Music is limited to no music or original code-generated music.
- User-supplied audio upload, licensed music search, storyboard editing,
  multi-shot revision UI, GPU scheduling, and publishing integrations are not
  implemented.
- No real render has been run by CI. CI can validate Python, tests, and the
  container build; a real render requires the separately provisioned host,
  source checkout, and Codex service identity.
- The worker must be operated as a separate service. Do not deploy it on the
  ordinary web API instance or an Android phone.
