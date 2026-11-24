# OpenCompany Brain Memory

## Status

The primary `opencompany_app` runtime now reads owner-approved Brain memories while preparing specialist work-item drafts. Memory records are stored in the same persistent SQLite database as the OpenCompany runtime.

This is a scoped retrieval layer, not an autonomous self-modifying policy engine. Retrieved text is reference context and is explicitly treated as untrusted data by the worker prompt.

## Memory scopes

- `company`: shared company-wide context.
- `business:physical-agency`: context for the physical-products agency only.
- `business:physical-brand`: context for the separately owned physical-products brand.
- `business:digital-products`: context for digital products only.
- `agent:<agent-id>`: private context for one registered agent.

Business scope validation uses the three registered business units. Agent scopes must refer to a currently registered agent.

## Owner workflow

All endpoints require owner authentication. The `/owner` control center includes a Brain memory panel for proposing records, filtering the review queue by approval state, and approving or rejecting proposals with an owner note. The dashboard uses the authenticated same-origin session and CSRF-protected write flow; it does not store the owner API key in browser storage.

1. Create a proposal with `POST /brain/memories`.
2. Inspect proposals with `GET /brain/memories?approval=proposed`.
3. Approve or reject one with `POST /brain/memories/{memory_id}/decision`.
4. Approved records become eligible for retrieval. Rejected and pending records are never injected into agent context.

Example proposal:

```json
{
  "scope": "business:physical-agency",
  "topic": "Supplier verification",
  "content": "Confirm production capacity using independent evidence.",
  "source": "owner",
  "confidence": 0.9
}
```

Example owner decision:

```json
{
  "approve": true,
  "note": "Reviewed and accepted by the owner."
}
```

## Runtime retrieval

When a specialist draft is prepared, the worker queries approved memories using the work-item title, objective, and assigned role. It retrieves:

- The matching business-unit scope.
- The assigned agent's private scope.
- The shared `company` scope.

Retrieval is lexical and deterministic in this version. It is not semantic embedding search. A maximum of 12 matching memory records are included, with each memory's content bounded before prompt construction.

The existing owner-written business context remains a separate feature. It is not silently promoted into Brain memory.

## Safety boundaries

- New records start as `proposed`.
- Only the owner-authenticated decision endpoint can approve or reject a proposal.
- A record can receive only one decision.
- Agent output cannot approve or edit Brain memory.
- Retrieved memory cannot override system, security, or task permissions.
- Memory retrieval does not authorize publishing, spending, customer contact, external commitments, refunds, or production changes.
- The runtime does not claim a task is revenue or a completed sale merely because it produced a draft.

## Current limitations

- Retrieval uses token overlap, not embeddings or a vector database.
- No automatic memory extraction from conversations or deliverables is enabled.
- No automatic learning or policy changes occur.
- Memory review is available in the owner dashboard and through the owner API.
- Dashboard filtering currently focuses on approval state; scope-specific filtering can be added later.
