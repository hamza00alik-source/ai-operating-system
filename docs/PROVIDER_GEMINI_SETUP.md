# Gemini AI Studio free-tier model setup

## Purpose

OpenCompany already has a provider-neutral OpenAI-compatible chat-completions adapter. Google documents an OpenAI-compatible Gemini endpoint, so an initial Gemini connection can use the existing adapter without adding a provider SDK.

This is a configuration guide only. It does not activate model execution, create an account, add a payment method, or make a model request.

## Free-tier facts and limits

- Google AI Studio and selected Gemini API models have a Free Tier with free input and output tokens.
- New Gemini API projects start on the Free Tier; setting up a billing account is required to move to paid tiers, not to use the Free Tier.
- Model access, quotas, and rate limits vary by model, project, and account. Check the live AI Studio rate-limit page and project dashboard before relying on a model.
- Google says content submitted on the Free Tier may be used to improve its products. Do not submit customer records, credentials, private business data, or other confidential information under this tier unless the owner has explicitly reviewed and accepted the current terms.
- Do not upgrade billing or attach a payment method for this setup.

Official references:
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/billing
- https://aistudio.google.com/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/openai

## Account setup

1. Open https://aistudio.google.com/ and sign in.
2. Create or select a Gemini API project under the Free Tier.
3. Check the model list and rate limits shown for that project. Only use a model explicitly available to the account on the Free Tier.
4. Create an API key only if the account allows it without enabling billing.
5. Store the key as a private environment secret on the runtime host. Never commit it to Git, a public issue, a screenshot, or a shared document.

The example model below is illustrative (gemini-3.8-flash); do not assume it is free or enabled for every account. Replace it with the exact model ID shown as available in the account's Free Tier.

## Private runtime configuration

Set these variables in the private host environment, not in a committed file:

```dotenv
AI_OS_MODEL_ENABLED=false
AI_OS_MODEL_BACKEND=openai_compatible
AI_OS_MODEL_PROVIDER=gemini
AI_OS_MODEL_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
AI_OS_MODEL_NAME=gemini-3.8-flash
AI_OS_MODEL_API_KEY=<your-private-Gemini-API-key>
AI_OS_AGENT_TOOL_CALLS_ENABLED=false
AI_OS_MODEL_MAX_REQUESTS_PER_STEP=1
```

Keep AI_OS_MODEL_ENABLED=false until the owner has reviewed the model, account tier, data terms, and limits. The request budget is set to one for an initial low-volume test; the code's hard ceiling remains four.

## Controlled activation procedure

Only after explicit owner approval:

1. Confirm the account is still on the Free Tier and the chosen model is listed as free.
2. Confirm the runtime has the correct private key, endpoint, and exact model ID.
3. Enable model execution only in the private runtime environment.
4. Submit one low-sensitivity test task with no customer data, credentials, or external-action request.
5. Confirm OpenCompany parses the structured JSON response and records the provider/model.
6. Check AI Studio usage and limits. Disable model execution again if any billing, privacy, quota, or output behavior is unclear.

A model request is an external network request even when it uses a free tier. Free access is quota-limited and does not guarantee continuous availability.

## Existing OpenCompany safeguards

- Model execution is disabled by default.
- Agent tool calls are independently disabled by default.
- The per-step model request budget is bounded.
- No paid-provider fallback is permitted.
- Model output is untrusted and cannot approve spending, publishing, customer commitments, or production changes.
- The Agency-Agents library supplies specialist role instructions; Gemini supplies inference only. OpenCompany retains its own CEO, task engine, memory, permissions, audit trail, and approval gates.

## Current status

This guide and the configuration preset do not mean Gemini is connected or running. A private API key, account-level Free Tier verification, owner approval, and a live smoke test are still required.
