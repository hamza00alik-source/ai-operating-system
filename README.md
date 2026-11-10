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

## Agency workforce catalog and owner console

The Owner Console includes a catalog of 283 specialist definitions across 18 departments from the MIT-licensed \`hamza00alik-source/agency-agents\` repository, plus a 12-repository source inventory including the separate Automaton runtime reference and ten company/platform comparison repositories. These are source catalogs and architecture references, not 283 running processes. Each specialist prompt is inspectable from its source link. The current general-purpose agent execution runtime is still under development.

The Owner Console supports a secure browser session: sign in once with \`AI_OS_API_KEY\`, then use the HttpOnly, Secure, SameSite=Strict session cookie for up to 14 days (or until logout/cookie clearing). The raw owner key is not saved in browser storage. API-key header authentication remains available for external clients.

## Hosting
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the Enzonic Python hosting setup. Use a persistent writable data directory for SQLite; the default relative database path is suitable only when the working directory is persistent.

See [docs/ROADMAP.md](docs/ROADMAP.md).


## Private provider credential vault

OpenRouter credentials can be entered in the Owner Dashboard under **Provider credentials**. The server encrypts the key with Fernet before writing it to SQLite; the key is never returned by the API. Configure `AI_OS_CREDENTIAL_ENCRYPTION_KEY` and `AI_OS_API_KEY` as private hosting environment variables first. Credential writes require the owner key even in development.

The first route is hard-pinned to OpenRouter's `openrouter/free` free-model router. It does not configure a paid model fallback. OpenRouter controls free model availability and rate limits. Keep the encryption key backed up securely; losing it makes stored credentials unrecoverable. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).


## Bounded AI task execution

The Owner Console can queue a task for the in-service agent worker. The worker selects a specialist definition from the 283-role Agency Agents catalogue, retrieves that role's Markdown instructions from the public source repository as untrusted prompt context, asks the configured eligible free-confirmed model provider for a deliverable, then performs a separate CEO-style quality review call. Results and token/latency metadata are persisted in SQLite and shown in the task panel.

This is deliberately a bounded first execution runtime. It performs text-only research, planning and drafting. It has no shell, filesystem, browser, MCP, email, payment, store, publishing or customer-contact tools. It cannot perform external side effects. Free-model availability and rate limits are controlled by the provider; if the configured free model is unavailable, the run fails and reports the error rather than using a paid fallback. Do not classify the catalogue as 283 concurrently running agents: one selected specialist plus one CEO review are invoked per task run.


## Persistent company AI brain (initial implementation)

The AI Brain is a provider-independent subsystem stored in the same persistent SQLite database as company operations. It automatically records completed agent-run outcomes as experiences, creates proposed reusable memories, and retrieves only owner-approved memories into future lead-specialist prompts. Owners can inspect, approve, or reject proposed memories in the **AI Brain** dashboard section or through `/brain/status`, `/brain/memories`, and the owner-authenticated `POST /brain/memories/{id}/review` endpoint.

This first version uses local lexical retrieval and SQLite; it requires no embedding service, extra model call, or separate training job. It does not train a new neural network, create a foundation model, or eliminate inference compute. It reduces repeated context-building by retaining approved company knowledge, while advanced reasoning still uses the configured model gateway. The owner must review proposed lessons before they can influence future agents. Only successful completed runs are recorded as experiences; failed runs are not treated as lessons.


## Free-provider failover

Company task stages may use only providers that are configured and explicitly owner-confirmed as free. The gateway never upgrades billing, selects a paid model, or falls back to an unconfirmed endpoint. If every eligible provider is unavailable or out of quota, the task fails safely and waits for owner action or quota reset. Provider attempts and the provider used for each stage are recorded in run metadata.

**UnoRouter is excluded from company task routing.** Its current Terms state that it does not offer business-customer accounts. The legacy connector is retained only for owner-triggered personal connection tests and read-only catalogue inspection. Do not use a consumer UnoRouter account for company workloads unless the provider confirms the intended business use in writing. Use synthetic, non-sensitive prompts for personal tests; do not send customer, company, confidential, credential, or sensitive personal data.

- `GET /llm/unorouter/catalog` — owner-authenticated, read-only catalogue lookup.
- `POST /llm/unorouter/personal-test` — isolated owner-triggered personal test.
- UnoRouter is not eligible for `/llm/run`, agent stages, automatic provider failover, or company execution.
- The generic company provider router considers only other configured, owner-confirmed free providers; no paid fallback or automatic top-up is permitted.

