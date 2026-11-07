# Google Cloud Shell operator setup

This guide prepares the repository for a controlled Cloud Shell smoke test after GitHub development. It does not create a production deployment, enable a model, or connect external business accounts.

## 1. Check out the reviewed development branch

```bash
git clone https://github.com/hamza00alik-source/ai-operating-system.git
cd ai-operating-system
git checkout feat/agency-agents-foundation
git pull --ff-only
git submodule update --init --recursive
```

If the repository is already present in Cloud Shell, run the cd, git checkout, git pull, and submodule commands from its directory.

## 2. Install and verify the project

Python 3.11 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
python scripts/validate_agent_library.py
pytest
```

The library validator checks the 18 declared divisions, 283 Markdown specialist profiles, required top-level frontmatter, unique profile IDs, runbook references, and that the checked-out submodule matches the Git commit pinned by this repository.

Do not continue if validation or tests fail.

## 3. Create private owner credentials

Keep credentials outside the repository. This creates a private shell environment file under your home directory; it does not print the generated secrets.

```bash
mkdir -p "$HOME/.config/ai-os"
chmod 700 "$HOME/.config/ai-os"
python - <<'PY'
from pathlib import Path
from secrets import token_urlsafe

path = Path.home() / ".config" / "ai-os" / "env"
path.write_text(
    "export AI_OS_ENV=production\n"
    f"export AI_OS_API_TOKEN={token_urlsafe(48)!r}\n"
    f"export AI_OS_AGENT_SIGNING_KEY={token_urlsafe(48)!r}\n"
    "export AI_OS_DATABASE_URL=sqlite:///./data/ai_os.db\n"
    "export AI_OS_MODEL_ENABLED=false\n"
    "export AI_OS_EXTERNAL_ACTIONS_ENABLED=false\n",
    encoding="utf-8",
)
path.chmod(0o600)
print("Private AI OS environment created at", path)
PY
mkdir -p data backups
```

In every terminal used for the API or worker, load the same private environment:

```bash
cd ~/ai-operating-system
source .venv/bin/activate
source "$HOME/.config/ai-os/env"
```

Do not paste the token or signing key into GitHub, source files, screenshots, issue reports, or chat messages. If either secret is exposed, rotate it.

## 4. Start the owner API and dashboard

In the first terminal:

```bash
cd ~/ai-operating-system
source .venv/bin/activate
source "$HOME/.config/ai-os/env"
uvicorn ai_os.api:app --host 0.0.0.0 --port 8000
```

Use the Cloud Shell Web Preview for port 8000 to open the dashboard. Enter the owner API token from the private environment file when prompted. The HTML shell is public to the preview, but operational API routes require the owner token.

Keep this as a development smoke test. Do not expose the service directly to the public internet or treat Cloud Shell as a production host.

## 5. Verify the owner control plane

From a second terminal, load the same environment and run:

```bash
cd ~/ai-operating-system
source .venv/bin/activate
source "$HOME/.config/ai-os/env"
curl -fsS http://127.0.0.1:8000/health
curl -fsS -H "Authorization: Bearer $AI_OS_API_TOKEN" http://127.0.0.1:8000/runtime
curl -fsS -H "Authorization: Bearer $AI_OS_API_TOKEN" http://127.0.0.1:8000/models/status
curl -fsS -H "Authorization: Bearer $AI_OS_API_TOKEN" http://127.0.0.1:8000/actions/gateway/status
```

Expected safe initial state:
- API health is ok.
- Model execution is disabled.
- External actions are disabled and no production adapters are registered.
- The dashboard can display profiles, company runs, queue, research review, evaluations, improvement proposals, and training-data controls.

## 6. Do not start autonomous inference yet

The worker requires a deliberately configured model backend. The repository does not bundle a model and does not silently choose a paid provider.

Before enabling any model:
1. Confirm the provider and model's actual cost, quota, data-retention terms, and privacy behavior.
2. Verify that the selected backend is permitted to receive company task data.
3. For the optional CLI backend, verify that its browser, shell, file, account, and other tools are disabled. The CLI no-tools confirmation variable is an owner attestation, not a sandbox.
4. Run a controlled smoke test and verify that the CLI returns the exact JSON report format expected by the adapter.
5. Get explicit owner approval before enabling inference if any metered or paid use is possible.

Only after those checks should the owner configure the backend in the private environment file and explicitly set AI_OS_MODEL_ENABLED=true. Then start one worker in a separate terminal:

```bash
cd ~/ai-operating-system
source .venv/bin/activate
source "$HOME/.config/ai-os/env"
python -m ai_os.worker_service
```

Keep one worker process initially. The worker performs internal specialist analysis and returns reports to the CEO; it does not publish, message customers, spend, purchase, refund, or deploy.

## 7. Backups and shutdown

Create a verified SQLite snapshot when the API and worker are stopped:

```bash
source .venv/bin/activate
source "$HOME/.config/ai-os/env"
python -c "from ai_os.db_backup import create_database_backup; print(create_database_backup('./backups/ai-os.sqlite3'))"
```

Copy backups to a separate private location and restrict access. The helper does not schedule or upload backups. Do not restore or replace the live database while any application process is running.

Stop Uvicorn and the worker with Ctrl+C. Cloud Shell may stop or recycle; it is a development environment, not an always-on production service. Continuous unattended operation requires a separately reviewed host, monitoring, backup, secret-management, TLS, access-control, and recovery setup.

## Current release boundary

This setup verifies the API, dashboard, registry, database, and owner controls. It does not complete production integrations, autonomous external actions, self-hosted model training, or an always-on production deployment. See ROADMAP.md for remaining gates.
