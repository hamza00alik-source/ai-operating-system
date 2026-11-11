# UnoRouter automatic free-model catalogue

OpenCompany accepts one owner-provided UnoRouter API key and discovers the full free model pool automatically.

## Discovery rules

The owner-only `GET /settings/providers/unorouter/models` endpoint intersects:

1. `GET https://api.unorouter.com/api/pricing/catalog` — only base models currently marked `online=true`.
2. `GET https://api.unorouter.com/v1/models` authenticated with the saved API key — only model IDs that the key can actually access.
3. The key-visible model ID must end in `:free`. UnoRouter documents this suffix as the zero-cost route marker. Its catalogue's `is_free` field describes the base route; a base row may be paid while a separate `:free` variant exists.

The catalogue refreshes every five minutes in-process. The owner can force a refresh from the dashboard. If either catalogue cannot be read, or no matching models remain, the adapter fails closed.

## Routing

The gateway rotates across the discovered free models. If a model is unavailable or rate-limited, it tries up to five other models from the same verified-free pool per request; later requests continue rotating through the wider catalogue. It never removes the `:free` suffix, rewrites a paid model ID, selects a paid route, or falls back to another provider.

Every successful completion must report an explicit provider cost of exactly zero. A missing cost, non-zero cost, unexpected model identity, or invalid response is rejected. The usage ledger records the actual model used.

## Owner setup

1. Enter the UnoRouter API key once in Owner Dashboard.
2. Confirm that only online catalogue entries with key-visible `:free` model IDs may be used.
3. Save encrypted credentials.
4. Press **Discover all free models** to view the current account-accessible catalogue.
5. Run the zero-cost connection test.

No per-model configuration is required. The list can change over time; refresh to discover additions and retirements.

## Scope and limitations

This is a chat-completions free-model pool. It does not automatically activate image, audio, or embedding model endpoints. Provider-specific rate limits still apply; rotation is best-effort and does not guarantee throughput or availability. Paid fallback is disabled.
