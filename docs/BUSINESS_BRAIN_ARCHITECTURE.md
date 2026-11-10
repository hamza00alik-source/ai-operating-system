# AIOS business brain and data isolation architecture

## Decision
AIOS uses one shared reasoning platform and three independent business environments:
- `physical-agency`: physical-products sales agency representing third-party suppliers/clients only.
- `physical-brand`: the owner's independent physical-products brand/business.
- `digital-products`: digital products and licensing only.
- `core`: legacy and internal operating-system work; not a shared business-memory pool.

## Shared platform
The businesses reuse the same provider-neutral model gateway, bounded execution worker, specialist catalogue, orchestration code, shared engineering components, and owner-approval workflow. AIOS model-provider credentials remain centrally managed because they operate the shared reasoning infrastructure. This shares technical capability, not business knowledge.

## Business-scoped records implemented
- Tasks, agent experience capture and proposed/approved/rejected brain memories.
- Exact-scope memory and research-evidence retrieval; no cross-business fallback.
- Captured research-source library and agent research context.
- Customer, revenue and expense ledger records; business summaries and owner-console filtering.
- Investor/partner contact records.
- Approvals generated from tasks or business expense records.
- Agent-run list queries are scoped through the owning task's business ID.
- Workflow instances and all generated workflow tasks inherit one selected business scope.
- Per-business integration credential vault for WooCommerce, Shopify, Meta, TikTok, PayPal, Stripe, marketplace and other supported provider labels. Secrets are encrypted at rest using the existing AIOS Fernet key; status APIs never return secret values. Only owner-authenticated endpoints can add, list status, or delete these credentials.

## Integration credential boundaries
- The model gateway's LLM provider keys are shared AIOS infrastructure credentials and are not duplicated per business.
- Business platform credentials are isolated by the composite key `(business_id, provider)`.
- The vault is storage and access-control groundwork only. It does not yet connect to or authorize actual storefront, advertising, marketplace, payment or social-platform APIs. No external account action is performed.
- Never place secrets in task text, research pages, memory content, logs, source control or dashboard output.

## Isolation and migration rules
- New tasks default to `core` for backward compatibility; the owner chooses a business environment explicitly.
- Every scoped endpoint validates its business ID against the four known scopes.
- Existing tasks, approvals, finance records, investor records, research sources and brain records remain in `core` during migration; no legacy data is copied into a business.
- New records default to `core` unless a business is explicitly selected.
- Reusable skills belong in version-controlled shared code/instructions, not confidential business memory.
- Owner review remains mandatory before a lesson becomes approved reusable memory.
- Internal code asset inventory and AIOS infrastructure configuration remain in `core`.

## Main interfaces
- `GET /business-environments`
- `GET /brain/status?business_id=physical-agency`
- `GET /brain/memories?business_id=physical-brand`
- `GET /tasks?business_id=digital-products`
- `GET /approvals?business_id=physical-agency`
- `GET /agent-runs?business_id=physical-agency`
- `GET /company/workflows/instances?business_id=physical-brand`
- `POST /company/workflows/technology-evaluation/start?business_id=physical-agency`
- `GET /business/summary?business_id=physical-agency`
- `GET /business/customers?business_id=physical-brand`
- `GET /business/revenue?business_id=physical-agency`
- `GET /research/sources?business_id=digital-products`
- `GET /business-integrations/physical-agency` (owner-authenticated; returns provider status only)
- `POST /business-integrations/physical-agency/woocommerce` (owner-authenticated; stores encrypted secret)

## Remaining isolation work
This is an implemented foundation, not a claim of complete multi-tenant or regulatory-grade isolation. Before storing confidential client data or onboarding staff/users, add row-level authorization for individual users, execution event/detail endpoint checks, scoped audit logs, backup/export boundaries, secret rotation/access audit, and tests for every route that can expose a record by identifier. Review all future tables and integrations for an explicit business owner. The owner console currently provides a single-owner business selector, not separate logins for each business.

The shared worker is one on-demand process and the specialist catalogue is shared. This is not three independent always-on agents and does not train separate neural networks.
