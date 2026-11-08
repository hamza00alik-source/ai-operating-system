# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this is a supervised operating-system foundation, not a fully autonomous company. The GitHub discovery worker is implemented as an initial capability; general-purpose AI agent execution, ecommerce, and social integrations are not yet production-connected.

## Principles
- Human approval before external or consequential actions.
- No spending, publishing, customer commitments, or production changes without explicit approval.
- Provider-independent architecture.
- Local-first development; SQLite is the default.
- Never commit secrets or customer data.

## Quick start
Requires Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn ai_os.api:app --reload
```

Open http://127.0.0.1:8000/owner for the visual owner console, or http://127.0.0.1:8000/docs for the API.

## Current starter capabilities
- Create and list work tasks.
- Create, list, approve, and reject approval requests.
- Persist records in SQLite.
- Health endpoint.
- API-key protection for operational endpoints outside development.

In development, operational endpoints are open for local testing. In staging/production, set `AI_OS_ENV=production` and a strong private `AI_OS_API_KEY`. Send it in the `X-API-Key` header. The app refuses to start in non-development mode if the key is missing. Keep `/health` public for uptime checks.

Approval records are workflow primitives, not a security sandbox. Do not connect production credentials until authorization, audit logging, and integration safeguards are reviewed.

## Supervised technology discovery (initial implementation)

The visual owner console at `/owner` can queue GitHub repository discovery scans and display persisted scan/candidate results. API endpoints are also available:

- `POST /discovery/scans` with `{"categories":["agent-frameworks","mcp-servers"]}`
- `GET /discovery/scans`
- `GET /discovery/candidates`

Run the combined background worker alongside the API (both processes must remain running):

```bash
python -m ai_os.worker_service
```

The combined worker processes both technology-discovery scans and queued Research Analyst runs. It uses SQLite leases so a second worker cannot normally claim the same active run; expired leases can be recovered after a process crash. Keep the worker process running on an always-on host for unattended queue processing.

The worker searches public GitHub repository metadata. Set `GITHUB_TOKEN` as a private environment variable to use authenticated GitHub API limits; never commit it. Without a token, GitHub documents a lower unauthenticated limit. Scans are queued by the API and processed by the worker. This is a GitHub-metadata discovery MVP, not a complete vendor/API price, security, or commercial-terms audit. Those fields remain explicitly unverified. See [docs/RESEARCH_DISCOVERY_PIPELINE.md](docs/RESEARCH_DISCOVERY_PIPELINE.md).

## Guarded live LLM gateway (new, requires owner configuration)

The API now exposes a provider-independent gateway:
- `GET /llm/providers` — provider configuration state (never returns secrets).
- `POST /llm/test` — sends a real small prompt and reports the returned text and latency.
- `POST /llm/run` — sends a user prompt to the selected provider.

The Owner Dashboard includes provider status, a live connection test, and a real inference panel. Supported adapter protocols are Gemini, Cloudflare Workers AI, and OpenAI-compatible chat completions (including compatible providers such as Groq and Mistral when configured with their official base URL).

**Fail-closed cost protection:** no provider is eligible by default. Configure the provider base URL, model ID, and secret as private server environment variables, then set its `*_FREE_CONFIRMED=true` only after checking the provider's current plan, model availability, quota, and billing settings. This flag is an owner assertion, not an automated guarantee that the provider will never bill. Do not attach a payment method or enable paid billing. Provider quotas can still be exhausted. The gateway never silently switches to a paid model.

Secrets are not stored in SQLite, returned by status endpoints, or meant to be pasted into the dashboard/chat. Add them only through the hosting environment-variable panel. If no provider is configured, live inference correctly remains unavailable.

See `.env.example` for the environment-variable names. The first persistent Research Analyst agent is now available:
- `POST /agents/runs` with `{"provider":"groq","goal":"Analyze this business brief..." }` queues an analysis-only run and returns HTTP 202.
- `GET /agents/runs` lists saved run history and output.
- The owner dashboard can queue work and refresh its run history.

The Research Analyst calls the guarded LLM gateway from the background worker. It does not browse, execute shell commands, call MCP tools, spend money, publish, or contact customers. This is one constrained background agent, not yet a general-purpose multi-agent planner or MCP execution runtime.

## Hosting
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the Enzonic Python hosting setup. Use a persistent writable data directory for SQLite; the default relative database path is suitable only when the working directory is persistent.

See [docs/ROADMAP.md](docs/ROADMAP.md).
