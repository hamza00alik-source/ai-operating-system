# Cinecode worker (experimental)

This worker is a local execution adapter for the AIOS Cinecode provider. It uses
the installed Codex CLI in non-interactive mode and never accepts a shell command
from a job. It is not enabled by default.

## Safety and billing gates

Run only inside a dedicated OS account, container, or VM with no access to the
AIOS API host filesystem, unrelated customer files, or production secrets.
Codex receives a workspace-write sandbox, and the AIOS worker token is removed
from the Codex subprocess environment. This is defense in depth, not a substitute
for OS/container isolation.

The worker refuses to start unless both are explicitly set:

- `CINECODE_EXECUTION_ENABLED=true`
- `CINECODE_BILLING_CONFIRMED=true`

The second flag is an operator assertion that Codex account usage and any other
metered services are understood and covered by the job's owner-approved budget.
Do not set it if usage may create an unapproved charge. No provider key, payment
method, or paid narrator is configured by this worker.

## Provisioning

1. Create a dedicated worker host with Python 3.11+, Node.js 22+, Git, FFmpeg
   (including ffprobe), and Chrome/Chromium/Edge with a working GPU driver.
2. Install and authenticate Codex CLI on that host using an account/usage plan
   whose billing has been reviewed. Do not put credentials in the job workspace.
3. Clone the upstream project at the exact commit below; do not use a moving
   branch in production:

   `git clone https://github.com/sarpstar/cinecode.git /opt/cinecode-source`

   `git -C /opt/cinecode-source checkout c8a3e7552699360a2b0142c9620882af2069eedb`

4. Provision a private writable work directory owned by the worker account.
5. Set the environment variables below using the host's secret/configuration
   manager. Never commit real values to Git.

| Variable | Required value |
|---|---|
| `AIOS_API_URL` | AIOS public HTTPS origin |
| `VIDEO_CINECODE_WORKER_TOKEN` | Unique provider-specific worker secret |
| `CINECODE_SOURCE_DIR` | `/opt/cinecode-source` |
| `CINECODE_EXPECTED_COMMIT` | `c8a3e7552699360a2b0142c9620882af2069eedb` |
| `CINECODE_WORK_ROOT` | Private writable job workspace root |
| `CINECODE_EXECUTION_ENABLED` | `true`, only after host review |
| `CINECODE_BILLING_CONFIRMED` | `true`, only after usage/billing review |
| `VIDEO_WORKER_ID` | Stable unique worker identifier (optional) |

Optional controls: `VIDEO_POLL_SECONDS` (5), `VIDEO_LEASE_SECONDS` (180),
`VIDEO_HEARTBEAT_SECONDS` (15), `CINECODE_JOB_TIMEOUT_SECONDS` (3600),
`CINECODE_MAX_DURATION_SECONDS` (900), `CINECODE_MAX_ARTIFACT_BYTES`
(300 MB, matching the API artifact endpoint), `CODEX_BIN`, `FFPROBE_BIN`, `PYTHON_BIN`, and `CHROME_BIN`.

## Run

From the AIOS repository root:

`python workers/cinecode_worker.py`

For each job, the worker copies the pinned kit into a separate cinecode-kit/ folder and creates the film-project/ as its sibling, then reads the upstream AGENTS.md and SKILL.md. It runs Quick mode by default (Film mode and purpose can be set in job parameters), uses the recommended defaults without interactive questions after owner approval, and uploads the production report to private AIOS storage before the MP4. Both downloads require owner authentication; terminal failed jobs clean up report sidecars. Codex is started with --skip-git-repo-check because the disposable workspace is not a Git repository.

The worker reports sanitized runtime capabilities (agent/runtime/browser versions, free disk space, and pinned source revision) on each poll. GPU is deliberately reported as unverified until a real render succeeds. It claims only owner-approved Cinecode jobs, creates a fresh UUID-named
workspace, copies the pinned Cinecode source without Git metadata or symlinks,
runs Codex with workspace-write sandboxing, sends lease heartbeats, checks the
result with ffprobe, and uploads the production report as a private sidecar, then streams the MP4 to AIOS private artifact storage.
Cancellation is checked on every heartbeat. Failed jobs use AIOS's bounded retry
policy.

The worker's default maximum artifact size is 300 MB, matching the API endpoint. Larger renders are rejected before upload. The worker does not publish or schedule videos. Publishing remains a separate
owner-approved operation.

## Optional hardened Linux Docker profile

The repository includes a reproducible Linux worker image and Compose profile:

- `workers/Dockerfile.cinecode` installs Node 22, Python 3, Chromium, FFmpeg/ffprobe, Git, and a pinned Codex CLI release.
- `workers/docker-compose.cinecode.yml` runs as an unprivileged UID, with a read-only container root, dropped Linux capabilities, no-new-privileges, bounded PIDs/memory/CPU, a private writable job volume, and a dedicated Codex home mount.
- `workers/.env.cinecode.example` is the environment template. Copy it to `workers/.env.cinecode` and enter real secrets only on the worker host; never commit that file.

On a dedicated Linux workstation with Docker Compose:

1. Create a separate Codex home used only by this worker, authenticate Codex CLI into it, and make the dedicated directory writable by container UID 10001. Do not mount your everyday developer home or other provider credentials.
2. Copy `workers/.env.cinecode.example` to `workers/.env.cinecode`; set the AIOS HTTPS URL and the unique Cinecode worker token. Keep both execution gates set to `false` initially.
3. Export `CODEX_HOME_HOST` (the dedicated Codex home directory). The Dockerfile pins stable `@openai/codex` version `0.169.0` by default; override `CODEX_VERSION` only when deliberately selecting another exact release.
4. Build and start the worker:

   `docker compose -f workers/docker-compose.cinecode.yml build`

   `docker compose -f workers/docker-compose.cinecode.yml up -d`

5. Check container logs. With both safety gates false, the worker intentionally exits without connecting to or claiming jobs; this confirms the default-disabled behavior.
6. Only after the Codex account's billing/usage, dedicated credentials, host firewall, and isolation have been reviewed, set `CINECODE_EXECUTION_ENABLED=true` and `CINECODE_BILLING_CONFIRMED=true` in the private `.env.cinecode`, then run `docker compose -f workers/docker-compose.cinecode.yml up -d --force-recreate`. The worker should now appear online in the AIOS Owner Console and report its pinned source commit, installed versions, and available disk before you approve a Cinecode job.

The container profile does not create a cloud machine, GPU, Codex subscription, or API quota. Host firewall rules should restrict outbound traffic to the AIOS HTTPS API and the required Codex service endpoints; omit optional research/CDN access for the Quick-mode zero-external-assets profile. GPU passthrough through `/dev/dri` is optional and must be enabled only on a compatible Linux host. Without it, Chromium may fall back to slow software rendering.

## Verification boundary

Unit tests cover workspace path validation, secret filtering, symlink exclusion,
brief handling, and media metadata validation. A real render, GPU compatibility,
agent CLI authentication, cancellation under load, and private artifact delivery
must still be verified on the actual worker host before enabling production jobs.
