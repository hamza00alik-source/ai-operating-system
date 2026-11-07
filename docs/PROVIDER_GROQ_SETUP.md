# Groq free-plan model setup

## Purpose

OpenCompany already has a provider-neutral OpenAI-compatible chat-completions adapter. Groq exposes an OpenAI-compatible endpoint, so a dedicated SDK or provider-specific runtime is not required for the initial connection.

This is a configuration guide only. It does not activate model execution, create an account, add a payment method, or make a model request.

## Free-plan checks before use

1. Create or sign in to a Groq account and open its console.
2. Confirm that the account is on the Free plan. Do not select an upgrade or Developer plan.
3. Check the current model catalogue and the account's Free-plan limits. Model availability and quotas can change; do not assume every model in public examples is enabled for every account.
4. Create an API key only if the account allows it without upgrading. Store it as a private runtime secret, never in Git, a dashboard screenshot, or a committed .env file.
5. Confirm the provider's current data handling and retention terms before sending company, customer, or confidential information.

Groq documents rate limits by model and returns HTTP 429 when a limit is exceeded. A free-plan request should fail closed at the limit; OpenCompany must not switch to a paid tier or provider automatically.

Official references:
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/api-reference
- https://console.groq.com/docs/billing-faqs

## Private runtime configuration

Set these variables in the private host environment, not in a committed file:

```dotenv
AI_OS_MODEL_ENABLED=false
AI_OS_MODEL_BACKEND=openai_compatible
AI_OS_MODEL_PROVIDER=groq
AI_OS_MODEL_BASE_URL=https://api.groq.com/openai/v1
AI_OS_MODEL_NAME=openai/gpt-oss-20b
AI_OS_MODEL_API_KEY=<your-private-Groq-key>
AI_OS_AGENT_TOOL_CALLS_ENABLED=false
AI_OS_MODEL_MAX_REQUESTS_PER_STEP=4
```

The example model ID is only a starting point. Verify that it is currently available on the account's Free plan before use. If not, choose a model explicitly listed as free in that account and set its exact model ID.

## Controlled activation procedure

Do not enable the model merely by copying the preset. Keep `AI_OS_MODEL_ENABLED=false` until the owner has reviewed the account's plan, model availability, data policy, and limits.

For an approved test, set `AI_OS_MODEL_ENABLED=true` only in the private runtime environment, then:

1. Check `GET /models/status` for the provider/model configuration.
2. Submit one low-sensitivity test task with no customer data, credentials, or external-action requests.
3. Confirm the structured JSON response is accepted and the provider/model are recorded.
4. Check the Groq usage/limits dashboard and confirm no upgrade or paid usage occurred.
5. Disable model execution again if any plan, billing, privacy, or output behavior is unclear.

A model request is an external network request even when its plan is free. Free access is quota-limited and is not a guarantee of continuous availability.

## Existing OpenCompany safeguards

- Model execution is disabled by default.
- Agent tool calls are independently disabled by default.
- The per-step model request budget is bounded.
- No paid-provider fallback is permitted.
- Model output is untrusted and cannot approve spending, publishing, customer commitments, or production changes.
- The Agency-Agents library supplies specialist role instructions; Groq supplies inference only. OpenCompany retains its own CEO, task engine, memory, permissions, audit trail, and approval gates.

## Current status

This guide and the configuration preset do not mean Groq is connected or running. A private API key, account-level free-plan verification, owner approval, and a live smoke test are still required.
