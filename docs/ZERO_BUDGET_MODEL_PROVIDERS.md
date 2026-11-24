# Zero-Budget Model Provider Strategy

## Current status

The model gateway is provider-neutral and fail-closed. No live provider is enabled by default. This document records candidates for verification; it does not claim that an account key is configured or that real inference has been tested.

## Candidate routes

- **OpenRouter free variants:** current public documentation lists $0-priced free model variants. Its free plan currently publishes a 50-request/day baseline; individual free model variants also have per-minute limits. Use only an explicitly free model identifier, never a paid model ID, never purchase credits to raise limits, and disable paid fallback.
- **Groq:** published per-model rate limits are available, but rate limits alone do not establish a zero-cost entitlement. Verify the account and selected model in the provider console before enabling.
- **Cloudflare Workers AI:** the current free Workers allocation includes 10,000 Neurons/day. Some models require paid billing, and overage on a paid Workers plan can be billable. Only use a free-eligible model with a hard daily stop.

## Activation contract

A provider can be activated only when the owner supplies its credential and confirms the exact model and zero-cost entitlement. Configuration must include an explicit free billing mode, a fixed model ID, bounded output, request rate limits, quota monitoring, and fail-closed behaviour. No silent provider or model substitution is allowed. If the free quota is exhausted, work waits or is routed to another separately verified free provider; it never switches to a paid model.

## Implementation status

The candidate inventory is available through the core API. The gateway remains disabled until an adapter, credentials, account entitlement and live zero-cost test are verified.
