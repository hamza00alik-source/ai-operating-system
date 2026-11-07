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
