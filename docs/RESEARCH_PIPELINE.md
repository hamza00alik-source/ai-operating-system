# Opt-in web research

## Current behavior

The research adapter uses Exa's official `POST https://api.exa.ai/search` endpoint.
It is **disabled by default** because Exa is a metered service. No key is bundled,
no fallback provider is silently selected, and no search runs on startup or in
the background. The API accepts at most five results per manually requested
search and requests result highlights only.

Enable it only after the owner has independently reviewed current provider
pricing and explicitly chosen to permit charges on the private runtime:

- Set `AI_OS_RESEARCH_ENABLED=true`.
- Set `EXA_API_KEY` as a private environment secret; never commit it.
- Keep the API protected by the owner token.

When disabled or missing a key, `GET /research/status` reports the reason and
`POST /research/search` fails closed without contacting Exa.

## Evidence and trust boundary

Each result with an HTTPS URL, title, and non-empty highlight becomes a
`candidate` knowledge item. It records the source URL/title, publication date
when supplied, access time, and the query tags. Search ranking, highlights,
and publication dates are not proof of truth. Candidates remain unavailable
to specialist retrieval until an owner reviews and accepts them through the
existing `/knowledge/{item_id}/review` workflow.

The system does not crawl arbitrary URLs, execute page content, follow links,
publish reports, create business tasks automatically, or accept provider
content as instructions. Search errors are sanitized; API keys are not returned
in status or logs. A single request makes at most one provider call; there are
no retries or hidden fallback calls.

## Zero-budget mode

Leave the feature disabled. The existing owner-reviewed `POST /knowledge`
workflow remains available for manually supplied source notes. This does not
provide autonomous web discovery, but it creates no search-provider charges.
