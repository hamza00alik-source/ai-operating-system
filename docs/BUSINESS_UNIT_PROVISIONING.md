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

The owner-authenticated endpoint `GET /business-units/{business_id}/activation-readiness` returns a non-mutating checklist. It verifies that all seven registry scope identifiers are present and distinct, inspects the actual commercial SQLite schema for fixed business-ID allowlists and composite customer-scope foreign keys, checks the finance ledger's actual composite foreign keys and append-only triggers, and reports the missing credential, integration, memory, and asset enforcement adapters plus the separate owner activation approval.

For a newly provisioned unit, the report remains blocked. The customer-scope check can now pass because opportunities, quotes, and orders persist customer scope and the database enforces business/scope pairing and same-scope parent relationships. Integration/memory/asset adapters and separate owner activation approval remain blockers; finance and business-credential scopes are enforced by OpenCompany-owned persistence. The readiness report does not change registry status. There is deliberately no activation endpoint until all remaining storage and service boundaries are implemented and reviewed. Foundational units are reported as already operational; they are not re-activated.

A scope identifier alone is not isolation. The customer data path below is backed by composite database foreign keys; other scope identifiers remain non-operational until their own persistence adapters enforce them.


## Dynamic work-item identity (latest increment)

The work-item domain now accepts a syntactically valid business-unit slug rather than hard-coding only the initial four identifiers. This is identity extensibility, not permission to operate: every SQLite work-item persistence path (single save, audited save, batch plan save, and delegation approval) resolves the unit against the registry and rejects unknown or `provisioning` units. `core` remains the internal platform scope; the three foundational units remain operational. API and worker-queue checks remain in place as independent enforcement layers. No commercial schema or existing customer/order data was changed by this increment.


## Commercial persistence enforcement (latest increment)

Commercial write operations now resolve the owning business through the business-unit registry at the SQLite persistence boundary. Creating opportunities/products, creating quotes from an opportunity, changing quote/order/product/supplier states, and supplier registration require an operational unit; provisioning and unknown units fail closed even if a caller bypasses the API. Quote creation also verifies the opportunity's registered unit before accepting product lines, and supplier registration retains physical-goods and relationship-type constraints.

This enforcement now supports dynamically registered business IDs at the schema level. SQLite schema version 8 transactionally rebuilds the opportunity, product, quote, order, and supplier tables to remove their fixed business-ID allowlists. It preserves existing rows, the quote-item child table and its foreign keys, indexes and table triggers, validates row counts and foreign-key integrity, and restores foreign-key enforcement.

SQLite schema version 9 adds customer_scope_id to opportunities, quotes, and orders. It backfills each record from its registered business unit, then adds composite foreign keys so the business ID and customer scope must match the registry. Quotes must reference an opportunity in the same business/customer scope; orders must reference both a quote and opportunity in that same scope. The migration fails if existing commercial records cannot be mapped to a registered unit or if foreign-key validation fails. It retains the quote-item child table and its existing index. Existing supplier relationship types remain valid; newly created physical business units use the generic `supplier` relationship type, while the original agency and own-brand relationship rules remain strict.

Application writes still pass through the operational registry guard, so the schema does not authorize unknown or provisioning units. Opportunity, quote, and order scope values are derived from the owning registry record, not accepted from caller input. The readiness report now checks the actual composite foreign keys for those three customer-lifecycle tables. Finance-ledger scoping, credential/integration/memory/asset adapters, and separate owner activation approval remain blockers; no newly provisioned unit is activated by these migrations.

The migrations are applied automatically when schema-version-7 or schema-version-8 databases are opened. They preserve existing commercial customer/order rows and do not change the three foundational units.


The persistence guard reads the already-initialized registry directly and avoids executing registry DDL from inside a commercial transaction. If the registry is absent during an active transaction, the write fails closed rather than performing an implicit SQLite commit. Accepted-quote order creation rechecks operational eligibility immediately before inserting the order.


## Finance ledger isolation (SQLite schema version 10)

OpenCompany now owns a finance ledger in its own persistence layer; it does not reuse the legacy `ai_os` finance code. Each entry stores an integer amount in currency minor units, a three-letter uppercase currency code, a business ID, and a finance scope derived from the registered business unit. The caller cannot override the finance scope. Composite foreign keys bind entries to the correct business/finance-scope pair, and review events must reference an entry in that same pair.

Both finance entries and their review events are protected by database-level update/delete triggers. A separate registry trigger also prevents a business unit's finance scope identifier from being changed. Owner-authenticated API routes provide scoped listing, internal record creation, and append-only owner review decisions. Recording or approving an entry is strictly a record-keeping action: it does not initiate a payment, transfer funds, purchase goods/services, or authorize spending. External financial actions are not implemented.

Schema version 10 adds the ledger tables and constraints transactionally, creates the registry's composite finance-scope key, validates foreign-key integrity, and leaves all existing business units and commercial records unchanged. Activation readiness now checks the actual finance columns, composite foreign keys, and all four append-only triggers rather than treating the presence of any vaguely named finance table as sufficient.


## Business-specific credential isolation (SQLite schema version 11)

OpenCompany now has a separate encrypted credential vault for business-specific integration credentials. It is distinct from the platform-level provider vault: platform inference/GitHub credentials remain platform configuration, while a supplier, marketplace, or other business-specific credential is stored under that business unit's own `credential_scope_id`.

The vault encrypts each payload with AES-256-GCM using the dedicated `OPENCOMPANY_SECRET_ENCRYPTION_KEY`; authenticated additional data binds ciphertext to the business ID, credential scope, and credential key. Plaintext is never returned by the owner API. The owner can inspect credential names/revisions, store or rotate a credential, and explicitly remove it. The API does not connect to external services or test credentials as a side effect.

Credential change events are append-only and hash-linked to the core audit chain. A deleted secret leaves its non-secret history event. Composite foreign keys bind both secret rows and history events to the registered business/credential-scope pair, and a registry trigger prevents credential scope identifiers from changing. Provisioning units may have credentials stored in preparation, but this does not make them operational or authorize an external integration.

Schema version 11 creates the scoped tables, indexes, foreign keys, append-only history triggers, and immutable registry-scope trigger transactionally. Existing platform-level encrypted credentials are not migrated, rewritten, or exposed by this new per-business vault. Activation readiness verifies the encrypted columns, both composite scope foreign keys, history triggers, registry immutability, and the presence of the dedicated encryption key. This clears the credential-storage isolation blocker only; the integration adapter remains a separate blocker until external connections are independently scoped and approved.


## Business-specific integration registry (SQLite schema version 12)

OpenCompany now records third-party integration declarations under each business unit's immutable `integration_scope_id`. This registry is separate from platform-level model/provider configuration and separate from the encrypted per-business credential vault.

An integration declaration must reference a credential key already stored for the same business unit at registration time. Composite foreign keys enforce both the business/integration-scope pair and the business/credential-scope pair. Credential availability is checked dynamically when the registry is read; removing a credential does not become impossible just because an integration declaration exists. The registry records a bounded permission declaration, display name, provider key, and `pending_review` status. A provider can be registered only once per business unit. A paused business unit cannot register new integrations.

Only the owner-authenticated API can register a declaration, and the request requires explicit confirmation. The API exposes status and append-only registration history; it never returns credential material. Registration does not test, connect, authenticate with, or call the external provider.

Integration declarations are immutable at the database layer. Both declarations and their history are protected from update/delete; integration scope identifiers are immutable in the business-unit registry. If a linked credential is later removed, the declaration remains visible with `credential_available=false` and cannot be used for execution. Registration events are also written to the hash-linked audit chain. Schema v12 creates the registry, indexes, composite foreign keys, and immutable-history triggers transactionally.

**Important boundary:** this increment implements storage isolation and registration intent only. It does not implement OAuth, token refresh, webhook handling, permission enforcement at execution time, connection testing, or external action execution. Activation readiness therefore clears the integration-storage isolation check but deliberately retains `integration_execution_adapter` as a blocker, in addition to owner activation approval and the remaining memory/asset isolation work.


## Business-specific persistent memory (SQLite schema version 13)

OpenCompany now has owner-managed, versioned memory for each business unit. Every record is bound to the unit's immutable `memory_scope_id` by a composite foreign key. Reads require one business ID and never perform cross-business search. Owner-authenticated API routes support scoped listing, revision history, owner-confirmed writes, and owner-confirmed forgetting. Forgetting appends a tombstone revision so the item disappears from current memory while its historical versions remain append-only.

Memory content is limited to 20,000 characters and provenance to 500 characters. Basic secret-marker checks reject common credential-like strings; credentials belong in the encrypted business credential vault instead. This is a defensive filter, not a guarantee that arbitrary text contains no secrets. Agent-originated writes remain disabled until provenance, role permissions, and owner review are enforced.

Schema v13 creates versioned memory records, a latest-revision index, composite business/memory-scope foreign keys, append-only update/delete triggers, and an immutable registry memory-scope trigger. Activation readiness verifies these constraints, clears the storage-isolation blocker when proven, and retains a separate `memory_ingestion_adapter` blocker. This does not activate any business unit.


## Business-specific asset registry, private storage and malware scanning (SQLite schema versions 14–16)

OpenCompany records asset metadata under each unit's immutable `asset_scope_id`. Asset declarations are owner-confirmed and include a business-local key, title, type, plain filename, media type, SHA-256 checksum, declared byte size, and provenance. Composite foreign keys bind declarations and their event history to the same business and asset scope. Declarations and events are append-only; no global asset listing or cross-business lookup is exposed.

The private filesystem adapter writes bytes to a configured absolute private directory, derives an opaque directory from the business ID and immutable asset scope, accepts only UUID asset IDs, caps files at 100 MiB, verifies actual byte count and SHA-256, uses mode 0700 directories and mode 0600 files, publishes atomically without overwriting, and rejects symlinked path components. HTTP uploads stream to a private staging file with a bounded size before the adapter verifies and publishes the object. The complete request is not buffered in RAM. Uploads also sniff file signatures for supported GLB, PNG, JPEG, GIF, WebP, PDF, ZIP and UTF-8 text types; the client Content-Type header alone is not trusted. If the append-only lifecycle event cannot be committed after the file write, the API compensates by removing the uncommitted file.

The owner-authenticated `PUT /business-units/{business_id}/assets/{asset_id}/content` route requires `X-Confirm-Owner-Upload: true`, a previously declared asset, matching content type, and an explicit configured storage root. The server derives the asset scope and expected checksum/size from the trusted registry; clients cannot select a filesystem path or storage key. Schema v15 appends a business-scoped `stored_unscanned` lifecycle event only after byte integrity succeeds. Asset declarations remain immutable, storage events are append-only, and a stored asset cannot be overwritten.

For hosted use, configure `OPENCOMPANY_ASSET_STORAGE_PATH=/data/opencompany-assets` and `OPENCOMPANY_ASSET_STORAGE_DURABLE=true` only after attaching and verifying a persistent Railway volume at `/data`. Runtime refuses to enable uploads unless `/data` is an actual mount point and the path is absolute and contained under it. The repository's deployment guide documents the volume requirement, but the actual deployed mount and permissions have not been verified by this code change. Do not point this setting at an ephemeral container directory or a public/static web directory.

**Malware scanning (SQLite schema version 16):** OpenCompany now includes a fail-closed ClamAV adapter using the local Unix-domain socket `INSTREAM` protocol. The owner-authenticated `POST /business-units/{business_id}/assets/{asset_id}/scan` route requires `X-Confirm-Owner-Scan: true`; it streams bytes from the private scoped storage adapter to ClamAV, computes SHA-256 and byte count during scanning, and records a verdict only if those values still match the immutable storage event. The scan event is append-only and bound by composite foreign key to the exact stored asset/business/scope. A clean verdict changes the state to `private_scanned_clean` / `pending_delivery_approval`; an infected verdict changes it to `quarantined`. Scanner absence, socket permission errors, timeouts, malformed responses, and scanner errors fail closed. An owner-only `GET /business-units/{business_id}/assets/{asset_id}/download` route additionally requires `X-Confirm-Owner-Download: true`, checks the latest scan verdict is clean, re-verifies size and SHA-256 on the same open file descriptor before sending bytes, and responds as a private no-store attachment with `nosniff`. The authorization is recorded in the audit chain. There are no public URLs, signed links, customer downloads, agent downloads, or external delivery permissions. Configure `OPENCOMPANY_CLAMD_SOCKET_PATH` to a local clamd Unix socket and optionally `OPENCOMPANY_CLAMD_TIMEOUT_SECONDS`; no remote or paid scanning API is used. This adapter is not active unless a real local scanner is installed and its socket is configured. The scan endpoint is owner-confirmed and does not publish or deliver anything.

**Still blocked:** runtime proof that the configured volume is durable and a real ClamAV socket is configured/healthy; customer/agent recipient authorization, expiring links, revocation, and delivery approval. Owner-only downloads do not authorize customer or agent access. A successful upload is marked `private_stored_unscanned` / `pending_scan`; it is not downloadable or publishable. The API returns no storage key or public URL. Activation readiness continues to block asset activation and business-unit activation until the remaining controls are implemented and verified. No unit is activated.
