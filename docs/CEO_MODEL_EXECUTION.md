# CEO model execution boundary

## Phase 3 capability
The OS includes an optional OpenAI-compatible chat-completions adapter and a CEO review operation. It does not install a provider SDK or select a vendor.

## Explicit opt-in
Model execution is disabled unless all three are set:
- \`AI_OS_MODEL_ENABLED=true\`
- \`AI_OS_MODEL_BASE_URL\`
- \`AI_OS_MODEL_NAME\`

Optional: \`AI_OS_MODEL_PROVIDER\`, \`AI_OS_MODEL_API_KEY\` (secret; never commit), and \`AI_OS_MODEL_TIMEOUT_SECONDS\` (5-90).

Remote endpoints must use HTTPS. HTTP is permitted only for localhost. The status endpoint never contacts a provider.

## CEO review flow
1. Specialists submit reports to the persistent run.
2. CEO review gathers stored reports.
3. The model receives the CEO policy and reports as untrusted input.
4. The structured response is normalised and stored in SQLite with provider/model/time provenance.
5. The result is recommendations only; it cannot dispatch work, create approvals, publish, message, spend, refund, or change production.

Endpoint: \`POST /ceo/review/{run_id}\`

## Limits
- OpenAI-compatible chat-completions only; provider-specific APIs need another adapter.
- No provider is configured or enabled by default; this change makes no model call.
- Free-tier quotas, privacy, retention, and terms vary; free does not mean always-on.
- Local Ollama requires a separate computer/server. An Android phone is not treated as a reliable always-on model host.
- This is one bounded review call, not an autonomous multi-agent loop or scheduler.
- Current authentication is single-owner, not role-based agent authentication. Keep private/local until role-level authorization and deployment hardening are complete.


## Zero-spend Groq mode

For a no-paid-fallback configuration, set `AI_OS_FREE_ONLY=true`, then configure:

- `AI_OS_MODEL_BACKEND=openai_compatible`
- `AI_OS_MODEL_PROVIDER=groq`
- `AI_OS_MODEL_BASE_URL=https://api.groq.com/openai/v1`
- `AI_OS_MODEL_API_KEY` to a secret stored only in the runtime host
- `AI_OS_MODEL_NAME` to a model confirmed as eligible for the current Groq free tier
- `AI_OS_FREE_MODEL_ALLOWLIST` to the exact same model identifier

Free-only mode fails closed if any condition is missing or mismatched. It rejects command/CLI providers, other hosts, missing keys, and models not explicitly allowlisted. It does not retry, switch providers, upgrade billing, or fall back to a paid service. Provider quota exhaustion (including HTTP 429) is returned as a failed model request; the worker should defer or mark the job for later handling.

The allowlist is an owner configuration gate, not a live guarantee that Groq will keep a model on its free tier. Check the current model and rate limits in Groq Console before enabling. Never commit API keys to GitHub. This mode does not guarantee unlimited inference or uninterrupted availability.
