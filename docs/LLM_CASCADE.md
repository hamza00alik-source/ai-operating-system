# LLM cascade routing

This module adapts the selected MIT-licensed LLM endpoint directory's core cascade
idea to AIOS rather than importing its entire standalone toolkit.

## Configure providers

Set `AI_OS_LLM_PROVIDERS` to a JSON array for additional providers. Authenticated entries use
`name`, `base_url`, `model`, `api_key_env`, and `free_tier_confirmed`. An entry with
`auth_style: "none"` may omit `api_key_env` and sends no Authorization header.
Put actual API keys in environment variables only; never in this JSON or Git.

Example (only mark free after checking the provider's current terms and quota):

```json
[
  {"name":"groq","base_url":"https://api.groq.com/openai/v1","model":"llama-3.3-70b-versatile","api_key_env":"GROQ_API_KEY","free_tier_confirmed":true},
  {"name":"gemini","base_url":"https://generativelanguage.googleapis.com/v1beta/openai","model":"gemini-2.0-flash","api_key_env":"GEMINI_API_KEY","free_tier_confirmed":true}
]
```

AIOS automatically includes `ovhcloud-anonymous` (`gpt-oss-20b`) even when no provider
configuration or API keys exist. OVHcloud documents anonymous access at 2 requests/minute
per IP and model; this is a low-rate public test path, not a guaranteed production SLA.
The router tries configured providers in order (with the built-in anonymous provider last),
falls through on HTTP/network/timeout
errors, and temporarily cools providers after repeated failures. Provider error bodies
and API keys are not returned to callers.

## API

- `GET /llm/providers`: configured provider status (existing endpoint)
- `POST /llm/test`: test one provider (existing endpoint)
- `POST /llm/chat`: free-first cascade chat

All operational endpoints require the AIOS API key outside development.

## Safety and limitations

- The built-in OVHcloud anonymous provider needs no key. Other providers still require their own credentials.
- The anonymous endpoint is rate-limited to 2 requests/minute per IP/model; availability and model names can change.
- Paid/uncertain providers are excluded unless `AI_OS_ALLOW_PAID_LLM=true`.
- Free-tier labels and quotas can change; verify current provider terms.
- Circuit-breaker state is process-local for now; durable quota accounting,
  admin controls, provider registry synchronization and agent role routing remain
  follow-up work.
- This endpoint only generates text. It cannot publish, spend money, or make
  customer commitments.
