# Provider eligibility and data boundaries

Last reviewed: 9 November 2026

## Company workloads

The company task runtime and automatic failover may use only providers that are configured, explicitly owner-confirmed as free, and not marked personal-test-only or experimental. The gateway must fail closed when no eligible provider exists. It must never silently select a paid model, attach billing, top up credits, or switch to a provider that has not passed the free-use gate.

Provider independence is preserved: the company runtime uses the generic provider interface, and the owner can select among eligible adapters. No provider is a mandatory architectural dependency.

## UnoRouter: personal testing only

UnoRouter is intentionally excluded from company task routing, specialist/collaborator/CEO stages, and automatic fallback. The separate owner-initiated personal-test endpoint remains available for synthetic, non-sensitive prompts.

UnoRouter's Terms of Service, last updated 20 October 2026, state that it does not currently offer business-customer accounts and that marked offers are unavailable to business customers. The provider also describes third-party routing and model-specific data handling. Therefore AIOS must not treat a consumer key or a `:free` model ID as authorization for company workloads.

- Free personal tests require an exact account model ID ending in `:free` and owner confirmation.
- Paid personal tests require explicit approval for that individual request.
- Never submit customer data, company confidential information, credentials, secrets, or sensitive personal data through this personal connector.
- Catalogue reads are read-only; they do not send prompts or invoke inference.
- This restriction is not a judgment that the service is technically unusable. It is an account/terms and data-governance boundary.

Official source: [UnoRouter Terms of Service](https://unorouter.com/en/terms) (last updated 20 October 2026).

## Human approval boundary

No social post, store listing, customer communication, payment, purchase, deployment, or other external side effect may occur without an explicit owner approval. Drafting, research, local evaluation, and read-only catalogue discovery may proceed within configured resource limits.

## Public framework versus private company data

Public source repositories may contain reusable code, schemas, documentation, and non-sensitive examples only. Company credentials, customer records, private memory, transaction data, and internal business plans belong in private storage and must never be committed to the public framework repository.

## Zero-budget policy

Free-tier labels are not guarantees. The owner must verify current pricing, account eligibility, quota, privacy, data retention, model terms, and commercial-use restrictions. Do not add a payment method or enable paid fallback as a workaround. If all eligible free routes are unavailable, stop and request owner action.
