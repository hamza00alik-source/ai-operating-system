# AI Operating System

A modular, human-supervised foundation for running an AI-powered company.

> Early development: this is a supervised operating-system foundation, not a fully autonomous company. The GitHub discovery worker is implemented as an initial capability; general-purpose AI agent execution, ecommerce, and social integrations are not yet production-connected.

## Independent OpenCompany rebuild status

The `clean-room-rebuild` branch and draft PR #105 contain a separate, independently authored OpenCompany core. It is not merged or deployed. The current `main` application, Docker entrypoint, Vercel routing, and Railway service still select the legacy `ai_os` application. See [the repository comparison audit](docs/REPOSITORY_COMPARISON_AUDIT_2026-11-10.md) for the capability comparison and release blockers.

The clean-room branch currently has ten original departments, 500 specialist role contracts (50 per department across 100 capability teams), ten department-manager roles, and one owner-subordinate executive orchestrator: 511 role contracts in total. The 500 specialist roles have distinct curated capability profiles and role-specific operating playbooks. The runtime supports CEO objective decomposition, manager-led team proposals, owner-approved specialist child tasks, durable queue execution, review-required deliverables, and manager synthesis after approved dependencies. These are role profiles, not 511 continuously running agents. The worker fleet runs only explicitly admitted work; the system is not yet a fully autonomous company, and ecommerce, social publishing, customer messaging, payments, and other external business actions are not production-connected.


## UnoRouter company inference provider

UnoRouter is a first-class provider in the independent OpenCompany runtime, not a read-only catalogue or personal-test-only integration. The new core includes an OpenAI-compatible chat adapter and a gateway factory usable by AgentExecutor. Owner configuration requires a private `OPENCOMPANY_UNOROUTER_API_KEY`, an exact `OPENCOMPANY_UNOROUTER_FREE_MODEL` ending in `:free`, and `OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true`. The provider status endpoint reports configuration without exposing credentials. Paid model IDs and paid fallback are excluded; non-zero provider-reported cost is rejected. See [the UnoRouter adapter guide](docs/UNOROUTER_FREE_ADAPTER.md).

This implementation does not import or reuse the legacy AIOS provider code. The new runtime still requires deployment configuration and an owner-authorized live inference test before real provider execution can be claimed as verified.

## Principles
- Human approval before external or consequential actions.
- No spending, publishing, customer commitments, or production changes without explicit approval.
- Provider-independent architecture.
- Local-first development; SQLite is the default.
- Never commit secrets or customer data.

## Quick start
Requires Python 3.11+.

\`\`\`bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn ai_os.api:app --reload
\`\`\`

Open http://127.0.0.1:8000/owner for the visual owner console, or http://127.0.0.1:8000/docs for the API.

## Current starter capabilities
- Create and list work tasks.
- Create, list, approve, and reject approval requests.
- Persist records in SQLite.
- Health endpoint.
- API-key protection for operational endpoints outside development.

In development, operational endpoints are open for local testing. In staging/production, set \`AI_OS_ENV=production\` and a strong private \`AI_OS_API_KEY\`. Send it in the \`X-API-Key\` header. The app refuses to start in non-development mode if the key is missing. Keep \`/health\` public for uptime checks.

Approval records are workflow primitives, not a security sandbox. Do not connect production credentials until authorization, audit logging, and integration safeguards are reviewed.

## Supervised technology discovery (initial implementation)

The visual owner console at \`/owner\` can queue GitHub repository discovery scans and display persisted scan/candidate results. API endpoints are also available:

- \`POST /discovery/scans\` with \`{"categories":["agent-frameworks","mcp-servers"]}\`
- \`GET /discovery/scans\`
- \`GET /discovery/candidates\`
- \`GET /discovery/status\` — live GitHub API connectivity, public/authenticated quota, and worker status (never returns the token).

The production API starts the discovery polling worker in its FastAPI lifespan and uses the same persistent SQLite database. It retries after transient errors. This is currently a single-service worker design; multi-replica locking/leases still need hardening.

The worker searches public GitHub repository metadata. The Technology Discovery panel includes **Test GitHub API** and reports connectivity, quota, and worker status without exposing credentials. Set \`GITHUB_TOKEN\` as a private environment variable only if higher authenticated API limits are needed; never commit it. Public repository discovery works without a token, subject to GitHub's lower unauthenticated limits. Scans are queued by the API and processed by the worker. This is a GitHub-metadata discovery MVP, not a complete vendor/API price, security, or commercial-terms audit. Those fields remain explicitly unverified. See [docs/RESEARCH_DISCOVERY_PIPELINE.md](docs/RESEARCH_DISCOVERY_PIPELINE.md).

## Free API research catalog

The Technology Discovery panel can sync the structured public dataset from [IdoY12/awesome-free-ai-apis](https://github.com/IdoY12/awesome-free-ai-apis). AIOS imports provider descriptions, free-tier claims, policy notes (including prompt training and commercial-use caveats), confidence labels, primary-source URLs, and upstream probe status into its own SQLite catalog. The source dataset is CC0-1.0 and publishes a daily status file. This is research evidence, not a guarantee: provider quotas and terms can change, and upstream status checks do not prove that an AIOS account has access.

- `GET /discovery/provider-catalog` — read imported provider evidence.
- `POST /discovery/provider-catalog/sync` — owner-triggered, read-only catalog import.
- `bradAGI/awesome-free-inference` is retained as a secondary manual research lead; its visible verification badge is dated March 2026 and it has no structured provider dataset in the inspected repository.
- `dhaulagani/awesome-free-ai-apis` is excluded pending stronger evidence: the inspected README makes broad uptime/quota claims, but a repository LICENSE file was not found and per-provider primary-source evidence was not established.

The catalog sync never saves provider credentials, makes inference calls, enables a provider, or spends money. A provider must still be checked against official pricing, terms, region availability, privacy/training rules, and a live $0 account test before an owner may configure it in the LLM gateway. Unknown stays unknown.

## Guarded live LLM gateway

The API exposes:
- \`GET /llm/providers\` — provider configuration state (never returns secrets).
- \`POST /llm/test\` — sends a real small prompt and reports returned text, latency, and provider-reported token usage.
- \`POST /llm/run\` — sends a user prompt to the selected provider.

The Owner Dashboard includes provider status, a live connection test, and a real inference panel. Supported adapters are Google Gemini, OpenRouter, Cloudflare Workers AI, and OpenAI-compatible chat completions (including compatible providers such as Groq and Mistral when configured with their official base URL).

**OpenRouter setup:** use an API key from your own OpenRouter account and select a currently available model whose ID ends in \`:free\`. Free model availability and rate limits are controlled by OpenRouter and can change. The gateway does not unlock paid models or create free quota.

**Fail-closed cost protection:** no provider is eligible by default. Configure its base URL, model ID, and secret as private server environment variables, then set its \`*_FREE_CONFIRMED=true\` only after checking the provider's current plan, model availability, quota, and billing settings. This flag is an owner assertion, not an automated guarantee that the provider will never bill. Do not attach a payment method or enable paid billing. Provider quotas can still be exhausted. The gateway never silently switches to a paid model.

Secrets are not stored in SQLite, returned by status endpoints, or meant to be pasted into the dashboard/chat. Add them only through the hosting environment-variable panel. If no provider is configured, live inference correctly remains unavailable. Provider token counts are returned only when the upstream API reports them; this release does not yet maintain a durable aggregate usage ledger.

The gateway is an inference transport layer; it does not yet constitute a full multi-agent planner or MCP execution runtime.

## Legacy Agency-Agent catalogue (quarantined from the independent rebuild)

The Owner Console includes a catalog of 283 specialist definitions across 18 departments from the MIT-licensed \`hamza00alik-source/agency-agents\` repository, plus a 12-repository source inventory including the separate Automaton runtime reference and ten company/platform comparison repositories. These are source catalogs and architecture references, not 283 running processes. Each specialist prompt is inspectable from its source link. The current general-purpose agent execution runtime is still under development.

The Owner Console supports a secure browser session: sign in once with \`AI_OS_API_KEY\`, then use the HttpOnly, Secure, SameSite=Strict session cookie for up to 14 days (or until logout/cookie clearing). The raw owner key is not saved in browser storage. API-key header authentication remains available for external clients.

## Hosting
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the Enzonic Python hosting setup. Use a persistent writable data directory for SQLite; the default relative database path is suitable only when the working directory is persistent.

See [docs/ROADMAP.md](docs/ROADMAP.md).


## Private provider credential vault

OpenRouter credentials can be entered in the Owner Dashboard under **Provider credentials**. The server encrypts the key with Fernet before writing it to SQLite; the key is never returned by the API. Configure `AI_OS_CREDENTIAL_ENCRYPTION_KEY` and `AI_OS_API_KEY` as private hosting environment variables first. Credential writes require the owner key even in development.

The first route is hard-pinned to OpenRouter's `openrouter/free` free-model router. It does not configure a paid model fallback. OpenRouter controls free model availability and rate limits. Set a dedicated `OPENCOMPANY_SECRET_ENCRYPTION_KEY` (at least 32 characters) as a private hosting secret before saving provider credentials. It is deliberately independent of the owner login key; back it up securely because losing or rotating it makes existing stored credentials unrecoverable and requires re-entering them. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).


## Bounded AI task execution

The Owner Console can queue a task for the in-service agent worker. The worker selects a specialist definition from the 283-role Agency Agents catalogue, retrieves that role's Markdown instructions from the public source repository as untrusted prompt context, asks the configured eligible free-confirmed model provider for a deliverable, then performs a separate CEO-style quality review call. Results and token/latency metadata are persisted in SQLite and shown in the task panel.

This is deliberately a bounded first execution runtime. It performs text-only research, planning and drafting. It has no shell, filesystem, browser, MCP, email, payment, store, publishing or customer-contact tools. It cannot perform external side effects. Free-model availability and rate limits are controlled by the provider; if the configured free model is unavailable, the run fails and reports the error rather than using a paid fallback. Do not classify the catalogue as 283 concurrently running agents: one selected specialist plus one CEO review are invoked per task run.


## Persistent company AI brain (initial implementation)

The AI Brain is a provider-independent subsystem stored in the same persistent SQLite database as company operations. It automatically records completed agent-run outcomes as experiences, creates proposed reusable memories, and retrieves only owner-approved memories into future lead-specialist prompts. Owners can inspect, approve, or reject proposed memories in the **AI Brain** dashboard section or through `/brain/status`, `/brain/memories`, and the owner-authenticated `POST /brain/memories/{id}/review` endpoint.

This first version uses local lexical retrieval and SQLite; it requires no embedding service, extra model call, or separate training job. It does not train a new neural network, create a foundation model, or eliminate inference compute. It reduces repeated context-building by retaining approved company knowledge, while advanced reasoning still uses the configured model gateway. The owner must review proposed lessons before they can influence future agents. Only successful completed runs are recorded as experiences; failed runs are not treated as lessons.


## Free-provider failover

Company task stages may use only providers that are configured and explicitly owner-confirmed as free. The gateway never upgrades billing, selects a paid model, or falls back to an unconfirmed endpoint. If every eligible provider is unavailable or out of quota, the task fails safely and waits for owner action or quota reset. Provider attempts and the provider used for each stage are recorded in run metadata.

**UnoRouter is a first-class optional company inference provider in the independent OpenCompany runtime.** The adapter requires a server-side API key, an exact free model ID ending in `:free`, and explicit owner confirmation. It has no paid-model selection or paid fallback and rejects non-zero provider-reported cost. The live credential and real inference remain unverified; review the provider's current terms, billing state, privacy and data handling before sending confidential or customer data. Use synthetic, non-sensitive input for the first owner-authorized live test.

- New OpenCompany configuration: `OPENCOMPANY_UNOROUTER_API_KEY`, `OPENCOMPANY_UNOROUTER_FREE_MODEL`, and `OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true`.
- `AgentExecutor` resolves the configured UnoRouter gateway when no explicit gateway is injected.
- The legacy `/llm/unorouter/catalog` and `/llm/unorouter/personal-test` routes belong to the old application and are not the integration path for the independent rebuild.
- The new API/worker composition and manager-led multi-agent execution are still incomplete; enabling the adapter alone does not make the company runtime fully operational.




## Runtime and owner-controlled execution


The owner-only `GET /usage/model` endpoint exposes a durable inference-usage ledger (request counts, provider-reported token totals and cost, with the latest 100 secret-free events). Successful specialist calls write to the shared SQLite database; request IDs are idempotent. This is operational accounting, not a substitute for the provider's invoice or account dashboard.

The deployment exposes two distinct probes: `GET /health` is a process-liveness check; `GET /ready` verifies that owner runtime configuration exists and the persistent SQLite database passes `PRAGMA quick_check`. Readiness intentionally does not require a configured model provider, so the owner can open the dashboard and configure UnoRouter after first deployment. Railway's staged healthcheck uses `/ready`.

The independent OpenCompany API and worker now compose around one SQLite connection and transaction boundary. The API does not start workers at import or process startup.

- Run the API container with `python main.py`; its ASGI target is `opencompany_app.api:app`.
- The owner dashboard exchanges the owner bootstrap key for a revocable 12-hour HttpOnly session. Write requests require a CSRF token held in page memory. Sessions are stored as token hashes and can be revoked at logout.
- The owner must explicitly activate agent profiles, approve manager delegation proposals, and admit each READY assigned task to the durable worker queue.
- Queue admission verifies the active assignee, department, approved delegation state, and completed prerequisites; it atomically changes READY to QUEUED and appends audit evidence.
- Worker claims use the same SQLite connection, atomically change QUEUED to IN_PROGRESS, and append audit evidence. Specialist execution writes review-required deliverables; the owner dashboard is the review gate.
- The owner can explicitly start or stop the in-process worker fleet from the dashboard. The fleet processes only queued work assigned to ACTIVE profiles. It has no publishing, customer messaging, purchasing, or financial-action tools.
- The worker fleet is in-process by design for a single persistent Railway container and a single mounted SQLite volume. Do not run a separate worker service against the same SQLite file on another host or volume.
- `GET /owner/backup` downloads an owner-authenticated, consistent SQLite snapshot created with SQLite's online backup API and checked with `PRAGMA integrity_check`. The temporary server-side export is deleted after the response and marked `no-store`. Store downloaded backups securely off-host; this is a manual export, not automated offsite retention or a tested restore process.
- Set `OPENCOMPANY_DATABASE_PATH=/data/opencompany_core.sqlite3` and mount a persistent Railway volume at `/data`. Keep secrets in the host's secret-variable manager; never paste tokens into source files or logs.
- Set `OPENCOMPANY_COOKIE_SECURE=true` behind HTTPS. Set `OPENCOMPANY_BOOTSTRAP_WORKFORCE=true` and `OPENCOMPANY_AUTO_ACTIVATE_WORKFORCE=true` to provision and activate all 511 role profiles on startup. Set `OPENCOMPANY_WORKER_AUTOSTART=true` to keep the worker fleet running while the owner is offline; workers still process only explicitly owner-admitted queue entries, and queue admission is blocked until a confirmed free inference provider is configured. The owner bootstrap key is `OPENCOMPANY_OWNER_API_KEY`; Railway staging can reference the existing owner's `AI_OS_API_KEY` without revealing or changing its value.
- The UnoRouter provider requires `OPENCOMPANY_UNOROUTER_API_KEY`, `OPENCOMPANY_UNOROUTER_FREE_MODEL` ending in `:free`, and `OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true`. No paid fallback is enabled.
- API Anything read-only research requires `OPENCOMPANY_API_ANYTHING_BASE_URL` and `OPENCOMPANY_API_ANYTHING_TOKEN`. Use HTTPS for external endpoints; clear-text HTTP is accepted only for loopback development or Railway's `.railway.internal` private network. All calls are capped at tier 1 and no write endpoint is implemented. The specialist research broker can discover public sites, inspect operation schemas, choose only confirmed `readOnly=true` / `minTier=1` operations, reject credential/PII-like arguments, and attach bounded source results to specialist prompts as untrusted evidence.
- AI code evolution requires `OPENCOMPANY_GITHUB_TOKEN` and `OPENCOMPANY_GITHUB_REPOSITORY=hamza00alik-source/ai-operating-system`; `OPENCOMPANY_GITHUB_BASE_BRANCH=clean-room-rebuild` selects the rebuild branch. The token needs repository contents-write and pull-request-write permissions, but the runtime only creates isolated draft PRs and never merges.
- Standalone `worker_main.py` execution is intentionally disabled: it cannot prove an owner-authorized live zero-cost provider test in its own process. Use the API dashboard's in-process worker fleet, which starts only after the owner tests the configured free provider.

The current `vercel.json` still points at the legacy Railway service. Do not promote this branch or change production routing until the new Railway service has been deployed and verified with a persistent volume, owner session, worker queue, provider test, backup/restore and rollback rehearsal. No production migration or replacement is implied by a passing unit-test run.


## CEO planning, manager delegation, collaboration and learning

- An explicitly ACTIVE Chief Executive Orchestrator can decompose an owner objective into up to ten draft department tasks. The plan is validated for known departments and backward-only dependencies, then all draft tasks and audit events are persisted atomically.
- An explicitly ACTIVE department manager can use the configured free model to select exact capability identifiers from the 500-specialist catalogue. The deterministic planner can now select up to 50 specialists across multiple five-person teams in the same department (default 15), rather than being capped at one five-person team. The result is validated against the catalogue and saved as a delegation proposal. Owner approval is still required before child tasks are created; queue admission remains a separate owner-controlled step.
- Each of the 500 specialist roles now has an individual operating procedure generated from its unique role title, mission and capability contract: intake requirements, task steps, deliverable contract, quality rubric, escalation triggers and tool scopes. The procedure is injected into the role's execution prompt.
- Agent handoffs are persisted with sender/recipient identity checks, artifact provenance, state transitions and hash-linked audit events.
- Owner review automatically records an outcome evaluation against the reviewed deliverable. The free model can turn selected evaluations into a proposed role-learning note; an owner must approve it and explicitly apply it before the note is injected into future prompts.
- AI code evolution can generate complete file replacements for up to three allowlisted source/test/documentation files and open a DRAFT pull request on a new feature branch. The branch is tested by GitHub Actions. It cannot modify secrets, deployment workflows or production configuration, and it cannot merge or deploy.
- Code evolution requires server-side `OPENCOMPANY_GITHUB_TOKEN` and `OPENCOMPANY_GITHUB_REPOSITORY`. The token is never returned by the API. The initial PR is draft and owner review is mandatory.
