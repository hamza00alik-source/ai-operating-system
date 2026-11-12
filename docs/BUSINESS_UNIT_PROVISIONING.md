# Isolated business-unit provisioning

## Why this exists

OpenCompany can explore any legitimate business model, not only the initial physical-agency, physical-brand, and digital-products businesses. An opportunity is not an operating unit. After research and explicit owner approval for launch planning, the owner may provision a separate internal business identity.

## Provisioning gate

The owner-authenticated endpoint `POST /venture-opportunities/{opportunity_id}/provision-business-unit` accepts only an opportunity whose lifecycle is `approved_to_launch`, and it requires `confirm_owner_approval: true`. Business IDs are unique lowercase slugs. The unit type and primary delivery class are explicit.

## Isolation boundaries

Each provisioned unit receives independent identifiers for:
- Internal namespace
- Customer records
- Finance ledger
- Credentials
- Integrations
- Business memory/context
- Product and delivery assets

These are scope identifiers, not pre-created external accounts or connected databases. The registry records the boundaries so later systems can enforce them. A new unit is created with status `provisioning`, never `active`. Operational scope resolution now fails closed for unknown and provisioning units; only the three registered foundational units (or a future explicitly activated unit) pass the operational resolver. Scope IDs are returned only after that check.

## Strict delivery classes

Every unit declares exactly one primary delivery class: physical goods, digital files, software access, professional service, media/content, license, or referral. The initial physical-agency and physical-brand units are physical-goods; the digital-products unit is digital-files. The registry rejects a digital-products unit configured to deliver physical goods and rejects a physical unit configured to deliver digital files. Customer orders must later be routed only to the unit and delivery class that owns the customer promise.

## What provisioning does not do

Provisioning does not create or activate agents, tasks, queues, websites, marketplaces, payment accounts, credentials, inventory, supplier contracts, or external integrations. It does not spend money, publish listings, contact customers, accept orders, or mark the opportunity as launched. Separate owner-approved implementation stages must connect these namespaces to operational services before the unit can become active. Work-item creation and executive-plan generation enforce this operational gate. Worker-queue admission independently checks the persisted work-item business ID against the registry, including the low-level queue insertion path, so API bypasses or forged in-memory task identities cannot enqueue work for a provisioning unit.

## Owner API

- `GET /business-units` — list foundational and provisioned units.
- `POST /venture-opportunities/{id}/provision-business-unit` — provision an isolated internal unit from an approved opportunity.
- `GET /business-units/{business_id}/events` — inspect append-only provisioning history.

The foundational three business records are registered with their original delivery classes. Existing operations remain unchanged by this registry.


## Activation readiness (read-only)

The owner-authenticated endpoint `GET /business-units/{business_id}/activation-readiness` returns a non-mutating checklist. It verifies that all seven registry scope identifiers are present and distinct, inspects the actual commercial SQLite schema for fixed business-ID allowlists and customer-scope columns, checks for finance/ledger/payment persistence, and reports the missing credential, integration, memory, and asset enforcement adapters plus the separate owner activation approval.

For a newly provisioned unit, the report is expected to remain blocked today. In particular, the commercial tables still constrain business IDs to the original three units, and their customer records do not yet persist the new customer scope. The readiness report does not change registry status. There is deliberately no activation endpoint until these storage and service boundaries are implemented and reviewed. Foundational units are reported as already operational; they are not re-activated.

This is a safety gate, not a claim that scope identifiers alone isolate data. Existing commercial records and schema constraints are preserved; no migration or customer/order data rewrite is performed by this increment.


## Dynamic work-item identity (latest increment)

The work-item domain now accepts a syntactically valid business-unit slug rather than hard-coding only the initial four identifiers. This is identity extensibility, not permission to operate: every SQLite work-item persistence path (single save, audited save, batch plan save, and delegation approval) resolves the unit against the registry and rejects unknown or `provisioning` units. `core` remains the internal platform scope; the three foundational units remain operational. API and worker-queue checks remain in place as independent enforcement layers. No commercial schema or existing customer/order data was changed by this increment.
