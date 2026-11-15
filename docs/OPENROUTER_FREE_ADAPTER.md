# OpenRouter Free Inference Adapter

The clean-room core now contains a real OpenAI-compatible HTTP adapter for OpenRouter free model variants.

## Activation

Set all three environment variables only after checking the selected model's current pricing:
- OPENCOMPANY_OPENROUTER_API_KEY
- OPENCOMPANY_OPENROUTER_FREE_MODEL (must be an explicit model ID ending in :free)
- OPENCOMPANY_CONFIRM_OPENROUTER_FREE=true

The adapter is not enabled by default. It uses one locked model ID, no paid router or fallback, zero request budget, and a persistent SQLite quota reservation. The default local quota guard is capped at 50 requests per UTC day and 20 per rolling minute. Failed outbound attempts still consume a reserved slot, matching the conservative treatment of provider request quotas.

If the key, model, or confirmation is missing, no gateway is created. Partial configuration fails closed. Never place keys in source control or expose them through API responses.

## Limits

This adapter does not prove that a model remains free forever. The owner must verify the model's current $0 pricing before activation. If the provider changes pricing, stop using it and remove the configuration. There is no paid fallback. Real inference remains unverified until an owner-configured credential is tested.
