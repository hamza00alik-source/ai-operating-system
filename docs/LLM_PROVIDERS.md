# LLM provider connectivity

AIOS now includes a provider-neutral adapter for providers exposing the
OpenAI-compatible Chat Completions API. This is an integration layer, not a
claim that every provider in a social-media list is free or currently available.

## Safety and cost controls

- No provider is active until you configure it.
- API keys are read from environment variables; never paste keys into GitHub,
  source files, chat, or screenshots.
- A live test sends the configured prompt to the selected provider and may use
  quota or incur charges.
- By default, a provider can be tested only when its configuration explicitly
  sets `free_tier_confirmed: true`.
- Setting `AI_OS_ALLOW_PAID_LLM=true` bypasses that guard and must only happen
  after the owner explicitly approves paid API usage.
- Verify the provider's current pricing, free-tier limits, model availability,
  commercial-use terms, retention policy, and rate limits before marking it
  free-tier-confirmed.

## Configuration

Set `AI_OS_LLM_PROVIDERS` to a JSON array in the hosting environment. Example
shape (replace the endpoint/model with values verified from the provider's
current official documentation):

```json
[
  {
    "name": "groq",
    "base_url": "https://api.groq.com/openai/v1",
    "model": "YOUR_CURRENT_SUPPORTED_MODEL",
    "api_key_env": "GROQ_API_KEY",
    "free_tier_confirmed": false
  }
]
```

Then add the secret `GROQ_API_KEY` in the host's secret/environment-variable
settings. Do not commit the key. Repeat entries for additional compatible
providers; each entry needs a unique name and an HTTPS base URL.

## Endpoints

- `GET /llm/providers` lists configured provider names/models and whether
  their keys are present. It never returns key values.
- `POST /llm/test` sends one short test prompt to exactly one named provider.
  Requires the normal AIOS API key outside development.

Example:

```bash
curl -X POST http://127.0.0.1:8000/llm/test \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $AI_OS_API_KEY" \
  -d '{"provider":"groq","prompt":"Reply with exactly: AIOS connection test passed."}'
```

The provider adapter currently supports OpenAI-compatible Chat Completions
endpoints. Providers with different authentication, request, or response
formats need a dedicated adapter before they can be added.
