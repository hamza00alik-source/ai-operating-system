# Free AI inference provider registry (research snapshot: 2026-11-08)

This registry distinguishes a recurring no-charge allowance from trial credits and from services that merely have a free web playground. "Free" is not a production SLA. Provider quotas, eligibility, model availability, data handling and terms can change; re-check the provider's own console and terms before enabling a route.

## Candidate providers

| Provider | Free-use classification | Useful integration shape | Important restrictions / decision |
|---|---|---|---|
| Google Gemini API / AI Studio | Ongoing free tier for eligible models/projects | Native Gemini generateContent API | Exact quota is project/model/account-specific; read live AI Studio limits. Free-tier prompts/responses may be used to improve Google products; do not send secrets or sensitive customer data. **Keep as primary candidate.** |
| Groq | Ongoing Free plan with model-specific RPM/RPD/TPM/TPD limits | OpenAI-compatible chat completions | Limits differ by model and organization and can change. **Keep as fast fallback.** |
| Cloudflare Workers AI | 10,000 Neurons/day on Workers Free; excess requires paid plan and fails/needs upgrade | Cloudflare REST/binding API | Some frontier models require paid billing. Enforce a hard daily budget at 10,000 neurons and only allow models explicitly documented as available on Free. **Keep as constrained fallback.** |
| SambaNova Cloud | Ongoing free allowance reported by current provider-limit audit: 20 requests/minute, 20 requests/day and 200,000 tokens/day per model, without payment method | OpenAI-compatible inference API | Confirm current account-specific model limits and terms before enabling. **High-priority candidate to integrate.** |
| Cohere | Trial/evaluation key: 1,000 API calls/month; chat generally 20 requests/minute | Cohere Chat API / supported OpenAI-compatible interface | Trial keys are not for production or commercial use. Suitable only for internal experiments, embeddings/reranking evaluation if terms allow. **Do not route customer-facing workloads.** |
| NVIDIA NIM API Catalog | Free developer access for prototyping/research/testing | OpenAI-compatible hosted model endpoints (model-specific) | No published universal rate limit; production/commercial use requires the applicable enterprise licence. **Development-only candidate.** |
| OpenRouter free models | Zero-price `:free` model variants within account-level limits | OpenAI-compatible API | Availability/routing and caps depend on model/provider; some providers may train on prompts. Restrict routing to explicitly free models and check privacy settings. **Optional fallback, not guaranteed capacity.** |

## Exclude from the "ongoing free API" pool

- **Mistral La Plateforme:** current official plan documentation says Free mode does not include API access; API keys and API usage require billing activation/pay-as-you-go. Do not count it as a free API provider.
- **Cerebras Inference:** current comparison reports only a one-time signup credit requiring a verified payment method, not an ongoing free allowance. Do not count it as a zero-budget provider.
- **Fireworks AI:** one-time starter credit only; exclude from recurring-free pool.
- **Hugging Face Inference Providers:** no free inference credit on a free account according to current comparison; exclude from recurring-free pool.
- **OpenAI API / Anthropic API / DeepSeek API:** no ongoing free inference allowance in the reviewed comparison; exclude.

## AIOS integration priorities

1. Gemini, Groq, SambaNova: primary model providers for internal analysis and agent workloads.
2. Cloudflare Workers AI: low-volume fallback with strict daily usage accounting.
3. OpenRouter: optional router, allow only model IDs explicitly marked free and apply provider privacy policy filters.
4. Cohere and NVIDIA: keep disabled for internal evaluation/development only until their terms and intended use are confirmed.

## Required controls before any provider is enabled

- Never infer "free" from a signup page, promotional credit, playground, or a provider's marketing headline.
- Store credentials server-side only; never expose secrets in HTML, browser storage, API responses, logs, commits, or GitHub Actions output.
- Store an explicit provider/model allowlist, observed quota, verification timestamp, terms URL, privacy classification and workload eligibility.
- Default every new provider to disabled. Require an owner confirmation for the exact provider/model and its current free terms.
- Reject unknown models and paid-only models; do not silently fall back to a paid route.
- Set hard request/token/day budgets below provider caps and stop on unknown pricing, billing activation, or quota ambiguity.
- Read rate-limit response headers and apply exponential backoff; do not evade limits with account rotation.
- Do not send personal, confidential, customer, payment, or credential data to free-tier models without an explicit privacy review.

## Sources

- Free-tier comparison checked 2026-11-02: https://www.benchleader.com/free-llm-api
- Groq official rate limits: https://console.groq.com/docs/rate-limits
- Cloudflare official Workers AI pricing: https://developers.cloudflare.com/workers-ai/platform/pricing/
- Cohere official rate limits: https://docs.cohere.com/v1/docs/rate-limits
- Mistral official plan and usage limits: https://docs.mistral.ai/admin/billing-usage/usage-limits
- Gemini official rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- OpenRouter free models: https://openrouter.ai/collections/free-models
- NVIDIA NIM catalog: https://build.nvidia.com/

This document is a research registry, not proof that any provider has been connected or live-tested in AIOS.