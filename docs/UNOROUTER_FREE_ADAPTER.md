# UnoRouter Free Inference Adapter

UnoRouter is a first-class inference provider in the independently authored OpenCompany runtime. It is not restricted to catalogue lookup or personal test requests: once the owner configures the server-side connection, the returned ModelGateway can be supplied to the specialist execution pipeline and used by managers, specialists, and executive orchestration.

## Owner configuration

Set these private server environment variables in the OpenCompany hosting environment:

- `OPENCOMPANY_UNOROUTER_API_KEY` — API key from the owner's UnoRouter account.
- `OPENCOMPANY_UNOROUTER_FREE_MODEL` — exact account-accessible model ID ending in `:free`.
- `OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true` — explicit owner confirmation that the selected route is currently free.

The adapter uses the fixed HTTPS endpoint `https://api.unorouter.com/v1/chat/completions`. It does not accept a caller-supplied base URL, so task content cannot redirect the API key to another host. The key is held in server memory for the request and is never included in status responses.

Partial configuration, a missing confirmation, or a model ID that does not end in `:free` disables the provider. No paid model IDs are eligible for automatic execution. There is no paid fallback.

## Runtime integration

The application can construct the configured gateway with:

```python
from opencompany_core.unorouter_adapter import configured_unorouter_gateway

gateway = configured_unorouter_gateway()
```

The gateway implements the common ModelGateway interface consumed by AgentExecutor; this makes the same owner-enabled provider available to any role using that execution service. The adapter sends non-streaming chat-completion requests with bounded output tokens and a 45-second timeout. Responses are size-limited and checked for the selected model identity. Transport errors are converted to safe provider errors without exposing response bodies or credentials.

The zero-cost gateway rejects any response that reports a non-zero cost. If UnoRouter is unavailable or rate-limited, the task receives a provider-unavailable result; this adapter does not silently select a paid route. A separately configured free provider may be added to the gateway by the application, but no fallback is configured by this adapter.

## Status and verification

`GET /providers/status` reports whether UnoRouter configuration is complete, the selected model, and whether the provider is enabled. It never returns the API key. `real_inference_verified` remains false until an owner-authorized live inference check has actually succeeded.

No credentials are committed to Git. Configure them only in the deployment environment. A `:free` suffix and owner confirmation are safeguards, not a permanent guarantee that provider pricing, account limits, or availability will remain unchanged. Monitor the UnoRouter account's own usage and billing controls. Do not enable paid billing or attach a payment method merely to increase free quotas.