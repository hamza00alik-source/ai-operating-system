# Product & R&D, WooCommerce and revenue operations integration

Status: development-branch integration; not deployed. This slice selectively ports reviewed modules from the older Product & R&D branch without merging its divergent history.

## Product & R&D studio

The owner dashboard now includes a Product & R&D workspace backed by SQLite workflow records and the existing OpenCompany work-item and approval system.

Owner-authenticated endpoints:
- `POST /product-rd/workflows`
- `GET /product-rd/workflows?business_id=digital-products`
- `GET /product-rd/workflows/{workflow_id}`
- `POST /product-rd/workflows/{workflow_id}/delegate-stage`
- `POST /product-rd/workflows/{workflow_id}/sync-stage`
- `POST /product-rd/workflows/{workflow_id}/generate-pilot`
- `GET /product-rd/workflows/{workflow_id}/artifacts/{artifact_name}`
- `POST /product-rd/workflows/{workflow_id}/stages/{stage_key}/complete`
- `POST /product-rd/workflows/{workflow_id}/return-to-production`
- `POST /product-rd/workflows/{workflow_id}/owner-review`

Workflow sequence: opportunity brief → product specification → production plan → artifact generation → automated QA → owner visual preview → packaging → listing packet → CEO review.

Safety:
- Every product workflow belongs to exactly one of the three commercial businesses.
- USD 0 cost ceiling; any non-zero recorded cost is rejected.
- Stage completion requires evidence and persisted artifact references.
- QA failure blocks progression and supports a recorded return-to-production loop.
- AI stage work is created as a draft work item. Department-manager proposals, task approval, queue admission and execution remain separate owner-governed actions.
- A stage can be synchronized only from a completed work item with a persisted deliverable that has passed owner review.
- Final approval is internal only. It does not publish, contact customers, purchase, spend or change accounts.

The current deterministic pilot generator creates an original 30-icon SVG sci-fi survival UI pack, contact sheet, manifest, README, draft license notice and ZIP package. It is not a 3D character/model generator and its automated QA does not establish visual quality or engine compatibility.

## WooCommerce read-only adapter

Owner-authenticated endpoints:
- `GET /integrations/woocommerce/{business_id}/status`
- `PUT /integrations/woocommerce/{business_id}/connection`
- `DELETE /integrations/woocommerce/{business_id}/connection`
- `POST /integrations/woocommerce/{business_id}/test`
- `GET /integrations/woocommerce/{business_id}/products`
- `GET /integrations/woocommerce/{business_id}/orders`
- `GET /integrations/woocommerce/{business_id}/payment-status`

Connection credentials are stored in the existing encrypted provider secret vault. Saving credentials validates their shape locally and does not contact the store. A separate explicit test performs a bounded GET request. Product, order and WooCommerce-recorded payment-status reads are implemented; order responses omit customer personal data. The payment-status view uses WooCommerce's `date_paid` field and order status only: it reports a platform-recorded paid signal, not bank settlement or independently verified receipt. No product write, listing publication, order status change, refund, fulfilment or customer communication is enabled.

The adapter uses strict HTTPS URL validation, bounded pagination and response size, a read-only HTTP method surface, and does not follow redirects. Account-specific connection is not verified until the owner supplies credentials, the encryption key is configured, and the test succeeds.

## Revenue operations ledger

Schema migration sequence:
- v7 → v8: persistent private storefront listing drafts.
- v8 → v9: commercial financial events.

Owner-authenticated endpoints:
- `POST /commercial/financial-events`
- `GET /commercial/financial-events`
- `GET /commercial/financial-summary`

Only owner-verified source references can be recorded. Duplicate source references are rejected. Totals are isolated by business unit and currency; no foreign-exchange conversion is implied. Physical-agency recognized revenue is agency commission only, not supplier sales value. The ledger is a recordkeeping layer: it never initiates payments, payouts, refunds or transfers.

## Verification and remaining gates

Automated tests cover workflow transitions, business isolation, audit integrity, failed-QA rework, deterministic package generation and structural QA, WooCommerce read-only request behavior, customer-data minimization, financial ledger idempotency and same-currency aggregation.

Still required before production:
1. Owner review of the product pilot and the legal/license suitability of its contents.
2. Provision and activate the required canonical specialist/manager roles.
3. Confirm a genuinely free model provider in the live environment before any AI work is queued.
4. Owner configures the dedicated encryption key and WooCommerce credentials; verify the read-only connection.
5. Add integration tests using a controlled WooCommerce sandbox.
6. Add Gumroad/itch.io/CGTrader adapters only after owner account eligibility, permissions, payout and terms checks.
7. Validate backup/restore, monitoring, deployment secrets, security review and recovery procedures.
8. Obtain explicit owner approval before any marketplace publication, customer commitment or financial operation.

This branch has not been merged to main or deployed.


## Opt-in autonomous Product & R&D maintenance

The durable scheduler and ProductRDCoordinator are now wired to the existing worker fleet's maintenance loop.

Default behavior is disabled. To opt in at deployment time:
- `OPENCOMPANY_PRODUCT_RD_AUTOMATION=true` enables the persisted maintenance job.
- `OPENCOMPANY_WORKER_AUTOSTART=true` and a successfully owner-tested zero-cost model provider are still required to start the worker fleet; without the running fleet, scheduled maintenance does not run.
- `OPENCOMPANY_PRODUCT_RD_AUTO_PROPOSALS=true` separately permits zero-budget manager planning proposals. It defaults to false and is effective only when Product & R&D automation is enabled.
- `OPENCOMPANY_PRODUCT_RD_AUTOMATION_INTERVAL_SECONDS` sets the persisted job interval (default 5 seconds).
- `OPENCOMPANY_AUTOMATION_LEASE_SECONDS` controls the restart-safe lease (default 300 seconds).

The scheduler persists job state, execution history and lease tokens in the same SQLite database. Expired leases are recorded as interrupted and become eligible for retry. Failures are recorded by exception type and backed off; raw exception messages are not persisted.

Coordinator actions are limited to:
- Create unassigned/manager-routed draft work items for eligible workflow stages.
- Optionally prepare a manager proposal through the zero-budget gateway; the proposal remains draft and requires owner approval.
- Generate the local OUTPOST SVG pilot and run structural QA.
- Synchronize only completed deliverables already approved through the normal owner review path.

It does not approve manager proposals, admit draft work to the queue, start child tasks, execute customer work, publish listings, send messages, change accounts or initiate payments. The owner still controls worker startup, model-provider verification, task approval and queue admission.


## Owner-console integration

The mobile-friendly owner console includes:
- Product & R&D workflow creation, stage status, manager proposal review controls, artifact links and automation status.
- WooCommerce business selector, encrypted credential save, explicit read-only connection test, and product/order read views. Credential inputs are cleared after a successful save; they are not written to browser storage.
- All dynamic result text is inserted as text, not HTML. Order views contain only the minimized, non-PII fields returned by the read-only adapter.

Owner-only Product & R&D automation status endpoint: `GET /product-rd/automation/status`. It reports whether the scheduler is configured, whether the worker fleet is running, manager-proposal opt-in, maintenance counters and job metadata. It cannot start or authorize any external action.


## Company-wide owner approval inbox

The owner console now combines manager delegation proposals, review-required deliverables, Product & R&D preview/CEO checkpoints, and external-action approval requests in one business-filterable inbox.

Agent-originated approval intents are extracted only from one bounded, strict JSON block in a worker deliverable. Unknown fields, unsupported action types, oversized strings, invalid amounts/currencies, multiple blocks and malformed JSON are rejected. The server derives the requesting agent, work item and business from the validated worker lease; model text cannot supply or override those identities.

Owner-only endpoints:
- `POST /external-approvals` — create an owner-originated pending request.
- `GET /external-approvals` — list requests by business/status.
- `POST /external-approvals/{request_id}/decision` — record an owner decision.
- `POST /external-approvals/{request_id}/cancel` — cancel a pending request.
- `POST /internal/agent-approval-requests` — separately authenticated internal agent submission endpoint; the worker runtime currently uses the trusted in-process recorder.

An approval decision of `approve` requires the owner to type `AUTHORIZE`. It changes the record to `authorized_not_executed` with a 24-hour expiry. Rejection and cancellation are also audited. The inbox explicitly states that authorization is not execution.

There is deliberately no executor, marketplace publisher, payment client, purchase flow, customer messaging client, production mutator or deletion handler in this feature. An approved record cannot trigger an external action. Each future action requires a separately reviewed, narrowly scoped executor and a second execution record.


## Operations and production evidence

Owner-authenticated diagnostics now include:
- `GET /workers/health` — queue counts, oldest queued age, expired leases, dead-letter count, fleet state, maintenance cycles/failures and free-provider availability. No queue payloads, lease tokens or credentials are returned.
- `GET /automation/jobs` — persisted schedule configuration and job status.
- `GET /automation/history` — bounded execution history without callback payloads.
- `GET /owner/production-readiness` — evidence snapshot of database path/mount, SQLite quick-check, schema v9, audit-chain validity, required configuration presence and worker state.

The production-readiness endpoint always reports CI, independent security review, backup/restore rehearsal and staging acceptance as unverified by the endpoint, and always returns `production_cutover_authorized=false`. It is not a certification or deployment control. The current worker queue health snapshot does not yet provide durable per-attempt provider/checkpoint history; that remains a separate workforce-reliability milestone.


## Durable worker execution history and cancellation

The queue now maintains:
- One `worker_attempts` row per lease attempt, with started/finished timestamps, status and bounded error code.
- One `worker_checkpoints` record for a completed specialist output before final persistence, allowing a retry to reuse the same deliverable rather than invoke the model again.
- Exponential retry backoff with a configured cap.
- Recovery of expired leases into retryable or dead-letter states, with interrupted attempts recorded.
- Owner cancellation: queued work is cancelled immediately; leased work receives a cooperative cancellation request and is finalized by the worker under its live lease.
- Atomic shared-database deliverable persistence that checks the lease token, lease expiry, cancellation flag, assigned agent and active agent state before moving the task to review and completing the queue row.

Owner-authenticated endpoints:
- `POST /work-items/{work_item_id}/cancel`
- `GET /work-items/{work_item_id}/execution-history`

Execution history returns attempt status/timing/error codes and checkpoint metadata only; it does not expose lease tokens, queue payloads, credentials or checkpoint content. The checkpoint currently represents a completed specialist output, not streaming intermediate reasoning. Cancellation is cooperative and cannot forcibly interrupt an arbitrary provider call while it is blocked.


## Latest development verification

Code head `9d20c17fe7b6c72b393dc332401c80900f7ebce3`:
- Full suite: 486 passed, 5 warnings.
- OpenCompany Core Tests: passed.
- Container build and non-root smoke test: passed.
- Python compileall: passed.

The regression suite now explicitly verifies that a completed specialist-output checkpoint prevents a second provider execution after a sink failure, and that leased-task cancellation remains cooperative, audited and finalized under the live lease.


## Owner-verified payout reconciliation preview

`POST /commercial/payout-reconciliation/preview` accepts a bounded statement-line list (maximum 500), a business unit, currency, payout reference and explicit owner verification. It compares each line to exactly one financial-ledger source reference in the same business and currency. Results distinguish exact matches, amount mismatches, missing references, ambiguous ledger references and duplicate statement references.

This is a read-only preview: it does not import or persist the statement, mark ledger rows as reconciled, connect to a payment provider, fetch bank data, initiate or verify a payout, or perform a financial action. A fully matched preview means only that the supplied lines match existing ledger references and amounts; it is not proof that a bank or marketplace actually settled the payout. Persistent statement ingestion, settlement evidence and payment-status adapters remain separate work.
