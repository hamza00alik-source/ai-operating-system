# Free-first execution model

AIOS includes a provider-neutral model adapter and a verified anonymous public
model preset. Paid fallback is not allowed in the example configuration.

## Verified public model path

The current example preset uses:

- Provider: OVHcloud anonymous OpenAI-compatible endpoint
- Model: `gpt-oss-20b`
- API key: not required
- Strict free-only mode: enabled in `.env.example`
- Model allowlist: `gpt-oss-20b` only
- Request pacing: at least 31 seconds between requests from one process

A GitHub Actions smoke test successfully called the public endpoint through
AIOS's own `generate_json` adapter and received a valid structured response
without credentials. See the [public model smoke workflow](../.github/workflows/public-model-smoke.yml).

The endpoint is public and rate-limited (documented at approximately two
requests per minute per IP/model). Availability, model support, data handling,
and terms can change. It is suitable for a limited prototype test, not a
production SLA. Prompts sent to it leave the AIOS host and are processed by the
provider. Do not send secrets, payment details, or sensitive customer data.

## Configuration

The example environment uses the exact endpoint and model, sets
`AI_OS_FREE_ONLY=true`, and allowlists only `gpt-oss-20b`. The model can be
paused with `AI_OS_MODEL_ENABLED=false`. Do not turn off strict free-only mode
unless the owner explicitly approves the possibility of paid provider use.

Other providers are rejected in strict free-only mode unless their exact
provider, endpoint, authentication requirements, and model are explicitly
supported and allowlisted. There is no automatic paid fallback.

## Agent execution

The standalone worker can run continuously using:

```bash
python -m ai_os.worker_service
```

It schedules dependency-ready specialist tasks, passes completed reports into
downstream work packets, and schedules a CEO review after all specialist and
delegated manager work is terminal. The worker and API must share the same
persistent database file.

The public model smoke test proves provider connectivity only. The end-to-end
integration test exercises the queue, model adapter, two specialist handoffs,
and CEO review using a simulated HTTP transport. Neither test proves that a
separately deployed host is configured or running continuously.

## Manual free-chat fallback

A manual prompt-only workflow remains available:

1. Create a work packet for an enabled agent using the API docs at `/docs`.
2. Copy the returned `prompt_text`.
3. Use a free AI chat interface you already have access to.
4. Review the result and evidence before bringing it back into AIOS.

## Hard cost and action controls

- Strict free-only mode is enabled in the example configuration.
- No paid model fallback is permitted by that mode.
- Agent tool calls remain separately disabled unless explicitly enabled.
- Publishing, customer messaging, spending, purchases, refunds, and deployment
  remain behind the owner approval boundary.
- Never store credentials in Git, source files, screenshots, or chat.
