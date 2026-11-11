# UnoRouter Free Inference Adapter

UnoRouter is a first-class inference provider in the independently authored OpenCompany runtime. It is not restricted to catalogue lookup or personal test requests: once the owner configures the server-side connection, the returned ModelGateway can be supplied to the specialist execution pipeline and used by managers, specialists, and executive orchestration.

## Owner configuration

For owner-managed configuration, open the dashboard's UnoRouter panel and save the inference API key once. Use the inference key from UnoRouter's Tokens page, not the separate account API-access token. The key is encrypted in the server-side vault and is never returned to the browser after saving.

OpenCompany imports the complete live public pricing catalogue and intersects it with the models visible to the saved key. The dashboard may display paid, offline, and unsupported entries for research, but these entries are explicitly marked blocked and are never selectable for inference. A model is eligible only when the catalogue explicitly says `is_free=true`, input/output/fixed prices are all exactly zero, its model ID ends in `:free`, it is online, type is `text`, chat is enabled, the supported endpoint includes `openai`, and the exact free ID is visible to the saved key. Image, audio, embedding, paid, unpriced, offline, and unsupported routes remain in the imported catalogue as blocked research entries. The `:free` variant is the authoritative free-route marker; the public base row's `is_free` flag may be false even when a separate free variant exists. Discovery is cached for five minutes, and the owner can refresh the catalogue from the dashboard without re-entering the key.

The saved routing policy uses the internal model selector `unorouter/free-catalog:free`. The adapter rotates across every discovered eligible free model and tries the entire eligible set per request; there is no five-model cutoff. A failed, timed-out, rate-limited, or retired route is skipped in favour of another confirmed-free candidate. A model ID ending in `:free` is UnoRouter's documented zero-cost route; if the compatible chat response omits a cost field, OpenCompany records $0 only for that explicit free route. Any reported non-zero cost or unexpected model identity is rejected by the zero-dollar gateway policy. UnoRouter may return the requested base model name without `:free`; OpenCompany accepts only that exact base-name normalization and retains the requested `:free` identity in its own ledger. **Global hard rule:** the shared ModelGateway excludes every `PAID_OWNER_APPROVED` provider regardless of request budget. Paid models and paid fallback are never used anywhere in this runtime. Existing saved single-model credentials are migrated to this automatic policy on runtime initialization without changing or re-entering the API key.

Environment-based configuration remains available for controlled deployments:

- `OPENCOMPANY_UNOROUTER_API_KEY` — inference API key.
- `OPENCOMPANY_UNOROUTER_FREE_MODEL` — either an explicit account-accessible `:free` model ID or `unorouter/free-catalog:free`.
- `OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true` — explicit owner confirmation of free-only use.

## Runtime integration

The application can construct the configured gateway with:

```python
from opencompany_core.unorouter_adapter import configured_unorouter_gateway

gateway = configured_unorouter_gateway()
```

The gateway implements the common ModelGateway interface consumed by AgentExecutor. When an AgentExecutor is constructed without an explicitly supplied gateway, it now resolves this owner-configured UnoRouter gateway automatically; this makes the same provider available to every role using that executor. The adapter sends non-streaming chat-completion requests with bounded output tokens and a 15-second per-model timeout, trying up to five candidates. Catalogue reads use bounded 12-second timeouts. Responses are size-limited and checked against the actual selected free model. Transport errors are converted to safe provider errors without exposing response bodies or credentials. Owner connection tests run as background jobs and expose a pollable status so a slow model does not make the browser abandon the test.

The zero-cost gateway rejects any response that reports a non-zero cost. If UnoRouter is unavailable or rate-limited, the task receives a provider-unavailable result; this adapter does not silently select a paid route. A separately configured free provider may be added to the gateway by the application, but no fallback is configured by this adapter.

## Status and verification

`GET /providers/status` reports whether UnoRouter configuration is complete, the selected model, and whether the provider is enabled. It never returns the API key. `real_inference_verified` remains false until an owner-authorized live inference check has actually succeeded.

No credentials are committed to Git. Configure them only in the deployment environment. A `:free` suffix and owner confirmation are safeguards, not a permanent guarantee that provider pricing, account limits, or availability will remain unchanged. Monitor the UnoRouter account's own usage and billing controls. Do not enable paid billing or attach a payment method merely to increase free quotas.