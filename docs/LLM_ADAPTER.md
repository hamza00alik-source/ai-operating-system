# Optional provider-neutral model adapter

**Status:** Implemented on the feature branch; CI verification pending. Not connected to API routes, agents, or background workers.

The adapter supports OpenAI-compatible chat-completions endpoints, including providers that expose that API shape. It is intentionally disabled unless explicitly enabled.

## Safety defaults

- No model request is made unless `AI_OS_LLM_ENABLED=true`.
- A provider name, HTTPS base URL, model name, and API key are all required.
- Plain HTTP is accepted only for loopback local model servers.
- Requests have a bounded timeout.
- The adapter does not retry or silently switch providers.
- Prompts, API keys, and provider response bodies are not written to application logs.
- This adapter does not determine whether a provider is free. Check current quotas, pricing, account limits, privacy terms, and commercial-use terms before enabling it.
- Do not use a trial/developer-only endpoint for live customer transactions unless its terms explicitly permit that use.

## Configuration

Set these as private environment variables only after the owner has approved a specific provider and its usage terms:

| Variable | Purpose |
|---|---|
| `AI_OS_LLM_ENABLED` | Must be exactly `true` to permit requests |
| `AI_OS_LLM_PROVIDER` | Human-readable provider identifier |
| `AI_OS_LLM_BASE_URL` | OpenAI-compatible API base URL, without `/chat/completions` |
| `AI_OS_LLM_MODEL` | Exact model identifier |
| `AI_OS_LLM_API_KEY` | Private provider key |
| `AI_OS_LLM_TIMEOUT_SECONDS` | Optional timeout, default 30 seconds; maximum 180 |

Example for a compatible provider (illustrative only; not an instruction to activate it):

```text
AI_OS_LLM_ENABLED=false
AI_OS_LLM_PROVIDER=groq
AI_OS_LLM_BASE_URL=https://api.groq.com/openai/v1
AI_OS_LLM_MODEL=<approved-model-id>
AI_OS_LLM_API_KEY=<private-secret>
AI_OS_LLM_TIMEOUT_SECONDS=30
```

Keep `AI_OS_LLM_ENABLED=false` until a specific provider/model is approved and a bounded test budget or genuinely free quota is confirmed.

## Current scope and next gates

The module currently exposes a synchronous `chat_completion` function for internal use. It is not yet called by the FastAPI application, task queue, or any department agent. Before integration, add role-based authorization, per-task usage limits, audit metadata that excludes secrets/prompts, cancellation, and a provider policy that prevents unapproved endpoints. Run the test suite in GitHub Actions and inspect its result before merging this branch.
