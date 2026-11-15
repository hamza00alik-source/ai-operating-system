# OpenCompany company structure

**Status:** Canonical business-structure charter for the standalone OpenCompany rebuild.

## Ownership and governance

The owner is the sole final authority for strategy, business identity, budgets, credentials, financial accounts, contracts, external commitments, customer promises, publication, production deployment, purchases, payments, and withdrawals. The Chief Executive Orchestrator coordinates the company and reports to the owner; it is not an independent legal owner and cannot approve protected actions on the owner's behalf.

OpenCompany operates three distinct business units. They may use shared internal capabilities, but they must not share business records, customer identities, supplier relationships, product catalogues, pricing, revenue, costs, or external account credentials by default.

## The three businesses

### 1. Physical-products agency — `physical-agency`

**Business model:** Represent third-party physical-product suppliers or manufacturers and earn only the agreed agency fee or commission.

- The owner manages and controls the Pakistan-side supplier relationships, sourcing, product quality, inventory/production coordination, export readiness, and physical supply chain.
- OpenCompany supports international market research, buyer-demand analysis, positioning, marketing drafts, inbound enquiry triage, sales coordination, and reporting.
- Products remain the supplier's/manufacturer's products unless a separate written arrangement says otherwise.
- Agency revenue is the agreed commission or fee, not the full supplier product revenue.
- No agent may bind a supplier, quote a final offer, promise stock/delivery, negotiate binding terms, or contact a buyer without the required owner approval.

### 2. Own physical-product brand — `physical-brand`

**Business model:** The owner's independently owned physical-product brand, with its own brand identity, catalogue, customer relationships, pricing, sales, finances, and operations.

- Keep brand assets, product specifications, supplier/production arrangements, inventory, costs, margins, orders, customer data, and sales records separate from the agency.
- A supplier or product used by the agency is not automatically part of the owned brand.
- Any transfer, shared supplier arrangement, shared stock, or cross-sale between the agency and brand requires an explicit owner decision and separately recorded terms.
- OpenCompany may research, draft product pages, prepare marketing, analyse performance, and coordinate approved workflows; publication, customer commitments, and financial actions remain owner-gated.

### 3. Digital-products business — `digital-products`

**Business model:** Create and sell digital products and software-related downloadable assets under a separate business identity.

- Keep digital product IP/provenance, source files, licences, version history, storefronts, platform accounts, customer records, pricing, revenue, and support records separate from both physical businesses.
- Do not assume a digital product is an agency deliverable or part of the physical brand.
- OpenCompany may research opportunities, produce draft assets, prepare listings, and support customer operations. Publishing, licensing commitments, paid generation, and financial actions require owner approval.

## Shared company services

The ten OpenCompany departments are shared capability functions, not ten additional businesses:

1. Executive Office — strategy coordination, priorities, cross-business reporting, and owner escalation.
2. Intelligence & Research — market, competitor, supplier, buyer, and opportunity research within the assigned business scope.
3. Product & Innovation — product discovery, specifications, validation, and development planning.
4. Engineering & AI Systems — OpenCompany software, AI runtime, integrations, security, and reliability.
5. Media & Creative Production — approved creative and multimedia production.
6. Marketing & Audience Growth — organic marketing, SEO, content, and channel strategy.
7. Revenue & Partnerships — pricing analysis, marketplace research, listing drafts, and partnership proposals.
8. Customer Experience & Operations — support preparation, order workflow coordination, and feedback analysis.
9. Finance & Risk — separate business-level cost/revenue analysis, controls, and risk escalation.
10. Organizational Learning & Quality — quality review, incident learning, and improvement proposals.

Shared-service work must still carry the relevant `business_id` whenever it relates to a specific business. Truly company-wide governance and platform maintenance may use `core`. A `core` record must not be used as a workaround to mix business-specific data.

## Data and authority boundaries

- Every business-specific work item, research record, deliverable, learning note, model-usage record, integration credential, customer/order record, supplier record, and financial record must retain its business identity.
- The three business units must have separate external account connections and authorization scopes. A credential connected for one unit must never authorize actions for another.
- Cross-business dependencies and context injection are denied by default. If a genuine inter-business project is approved by the owner, create an explicit, minimal, auditable handoff that exposes only the approved information; do not copy whole customer, supplier, pricing, or finance records.
- Internal AI work is draft/review work. No automatic publishing, buyer/supplier contact, purchases, payments, withdrawals, binding quotes, or customer commitments.
- The owner can pause any business or shared department without disabling the others.

## Implementation status

The new runtime currently has four internal work scopes: `core`, `physical-agency`, `physical-brand`, and `digital-products`. It enforces business scope on work items, dependencies, learning retrieval, queue views, and model-usage attribution. This is not yet full business data isolation: separate integration credentials, CRM/customer and supplier records, inventory, order systems, accounting ledgers, and marketplace connections remain to be implemented before those external workflows are enabled.

The organization role catalogue contains ten departments, 50 specialist role contracts per department (500 total), ten department-manager contracts, and one owner-subordinate Chief Executive Orchestrator contract (511 role contracts total). These are role definitions, not 511 continuously running agents.

## Canonical references

- [OpenCompany organization charter](OPENCOMPANY_ORGANIZATION.md)
- [Standalone application and API boundaries](OPENCOMPANY_CORE_APP.md)
- [Implementation roadmap](ROADMAP.md)
