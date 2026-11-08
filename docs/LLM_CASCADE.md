# LLM cascade routing

This module adapts the selected MIT-licensed LLM endpoint directory's core cascade
idea to AIOS rather than importing its entire standalone toolkit.

## Configure providers

Set `AI_OS_LLM_PROVIDERS` to a JSON array. Each entry has:
`name`, `base_url`, `model`, `api_key_env`, and `free_tier_confirmed`.
Put actual API keys in environment variables only; never in this JSON or Git.

Example (only mark free after checking the provider's current terms and quota):

```json
[
  {"name":"groq","base_url":"https://api.groq.com/openai/v1","model":"llama-3.3-70b-versatile","api_key_env":"GROQ_API_KEY","free_tier_confirmed":true},
  {"name":"gemini","base_url":"https://generativelanguage.googleapis.com/v1beta/openai","model":"gemini-2.0-flash","api_key_env":"GEMINI_API_KEY","free_tier_confirmed":true}
]
```

The router tries configured providers in order, falls through on HTTP/network/timeout
errors, and temporarily cools providers after repeated failures. Provider error bodies
and API keys are not returned to callers.

## API

- `GET /llm/providers`: configured provider status (existing endpoint)
- `POST /llm/test`: test one provider (existing endpoint)
- `POST /llm/chat`: free-first cascade chat

All operational endpoints require the AIOS API key outside development.

## Safety and limitations

- No provider key is created or inferred by this integration.
- Paid/uncertain providers are excluded unless `AI_OS_ALLOW_PAID_LLM=true`.
- Free-tier labels and quotas can change; verify current provider terms.
- Circuit-breaker state is process-local for now; durable quota accounting,
  admin controls, provider registry synchronization and agent role routing remain
  follow-up work.
- This endpoint only generates text. It cannot publish, spend money, or make
  customer commitments.
