# AIOS business brain architecture

## Decision
AIOS uses one shared reasoning platform and three independent business memory environments:
- `physical-agency`: physical-products sales agency representing third-party suppliers/clients only.
- `physical-brand`: the owner's independent physical-products brand/business.
- `digital-products`: the independent digital-products business.
- `core`: legacy and internal AIOS operating-system work; not a shared business-memory pool.

## Shared platform
The businesses reuse the same provider-neutral model gateway, bounded execution worker, specialist catalogue, orchestration code, common security controls, and owner-approval workflow. This shares technical capability, not business knowledge.

## Isolation rules implemented in this phase
- Every task has a `business_id`; new tasks default to `core` for backward compatibility.
- Agent memory retrieval is exact-scope only. There is no fallback from one business to another and no cross-business retrieval of `general` department memories.
- Experiences and proposed/approved/rejected memories are tagged with their business environment.
- Existing pre-migration records remain in `core`; they are not copied into the three business environments.
- Reusable skills belong in version-controlled shared code/instructions, not confidential business memory.
- Owner review remains mandatory before a lesson becomes approved reusable memory.

## Business environments
`GET /business-environments` lists the three businesses and internal core environment.
Create tasks with one of these `business_id` values: `physical-agency`, `physical-brand`, `digital-products`, or `core`.
Brain inspection endpoints accept a `business_id` query parameter, e.g. `GET /brain/status?business_id=physical-agency` and `GET /brain/memories?business_id=digital-products`.

## Important boundary
This is the first isolation layer for task routing and persistent AI memory. It does not yet claim full multi-tenant isolation for every existing table, integration credential, captured research source, business ledger, customer record, or dashboard view. Those need business ownership/scope fields and access checks before client-specific or confidential production data is stored. Until then, do not put client secrets or confidential cross-business data into global research sources or legacy global business records.

The shared worker is one on-demand process and the specialist catalogue is shared. This is not three independent always-on agents and does not train separate neural networks.
