# OpenCompany Treasury — implementation specification

## Goal

Turn OpenCompany from owner-entered financial records into a business treasury that can eventually accept real customer payments and execute authorized disbursements. The treasury is a capability layer, not a pretend bank account or an accounting-only dashboard.

## Business isolation

Every account, transaction, ledger entry, payment intent, payout, approval, provider event, and reconciliation record is scoped to one of:
- `physical-agency`
- `physical-brand`
- `digital-products`

Queries and provider credentials must not cross scopes. A shared provider account may be represented only when the owner explicitly declares it and allocations are independently recorded.

## Money representation

- Store monetary amounts as integer minor units (e.g. cents/paisa); never floating-point money.
- Currency is mandatory on every amount and transaction.
- Currency conversion is a separate, evidence-backed transaction. Never silently mix currencies.
- Store immutable transaction/ledger history. Corrections are compensating entries, not overwrites.
- Distinguish `pending`, `confirmed`, `failed`, `reversed`, and `disputed` states; don't treat a provider request as proof of settlement.

## Accounts and rails

Account registry records provider, account/wallet identifier (masked in UI), currency, business scope, capabilities, connection state, and owner-confirmed metadata. Credentials are kept outside SQLite in host secrets/environment or an approved secret store; status APIs must never expose them.

Adapters are capability-specific:
- inbound payment intents/checkout and provider webhook verification
- balance/settlement queries where the provider supports them
- outbound payouts/transfers where the provider supports them
- refunds only when supported and approved

No adapter is considered live until provider terms, country eligibility, account identity, fees, settlement timing, API scopes, and a safe test transaction have been checked.

## Inbound payment lifecycle

1. Create an owner-authorized payment request or checkout session for a business, order, currency, and amount.
2. Return a hosted checkout link or provider reference; never collect raw card details in OpenCompany.
3. Accept provider webhook events only after signature verification.
4. Persist provider event IDs with a uniqueness constraint for replay protection.
5. Reconcile payment/order/currency/amount and prevent overpayment or cross-business association.
6. Mark payment confirmed only after authoritative provider confirmation; create ledger entries atomically and idempotently.
7. Keep refunds/disputes separate and visible.

## Outbound lifecycle

1. Agent submits a structured spend request: business, agent/work item, vendor/payee, purpose, amount, currency, evidence, and budget category.
2. Treasury policy checks available settled balance (not pending funds), business budget, transaction limits, recipient allowlist, provider capability, and duplicate idempotency key.
3. Approval gate is required by default for transfers, refunds, withdrawals, and any new recipient. Agent autonomy may only be granted by owner-set bounded rules after a provider and policy have been validated.
4. After approval, adapter executes once using provider idempotency support where available.
5. Store request, approval, provider response, transaction state, and ledger records. Reconcile provider state; never report success on an unconfirmed request.

## Agent financial permissions

Agent access is policy-based and revocable:
- read scoped treasury summaries
- propose spend (no movement)
- spend within explicit per-agent/per-business limits only when owner enables that permission and the provider supports reliable idempotency and balance checks
- no ability to change treasury policy, approve its own request, add unrestricted recipients, change credentials, or withdraw funds to an owner-controlled personal destination

Default agent spend limit is zero. Owner approval is required for payments until a reviewed provider integration and permission policy are implemented.

## Ledger

Use a balanced, append-only double-entry journal:
- journal entry header (business, currency, reference, event, created timestamp)
- journal lines (account, debit minor units, credit minor units)
- validate debits equal credits per entry and currency
- no editing or deleting posted entries
- pending provider activity is kept in a separate status record until settlement/confirmation rules are met
- existing finance ledger is not overwritten or migrated implicitly; plan a reviewed migration

## Security and reliability

- Verify webhook signatures and timestamp/replay protections.
- Use provider idempotency keys, unique webhook event IDs, and unique external transaction IDs.
- Keep secrets out of repository, dashboard responses, logs, and event payloads.
- Require CSRF protection on owner-cookie writes; API key protection for owner endpoints.
- Rate limit payment request and transfer endpoints.
- Add explicit limits and allowlists. Fail closed on unknown status, currency, provider, or capability.
- Avoid auto-retry for money movement unless idempotency is guaranteed; reconcile uncertain outcomes before retrying.
- Record append-only audit events for request, approval, execution, provider confirmation, reconciliation, refund, and reversal.
- Never infer available cash from the internal ledger alone; display provider-confirmed balance and reconciliation timestamp.

## Staged delivery

1. **Treasury model (offline)** — scoped account registry, spend requests, approval policies, immutable journal, fake/sandbox adapter, and unit tests. No live credentials or money movement.
2. **Owner console** — balances labeled source and last-verified time, transaction history, approval inbox, spend requests, reconciliation and business-unit switching.
3. **Inbound sandbox** — one provider, test checkout and signed webhook, replay/idempotency tests; no real funds.
4. **Outbound sandbox** — one supported rail, test recipients, idempotency, failure/timeout/reconciliation coverage.
5. **Live-readiness review** — official provider terms, Pakistan availability, business/KYC eligibility, fees, security review, backups and operator procedure.
6. **Live enablement** — only after owner explicitly authorizes provider, credentials, limits and a controlled test. Production money movement is not part of automatic implementation.

## Definition of ready for real money

A provider connection must demonstrate verified webhook or API signatures, replay prevention, business isolation, exact currency/amount validation, idempotency, double-entry balance invariants, clear pending/settled states, audited approval, reconciliation, secret isolation, timeout recovery, and sandbox tests. Provider-specific country eligibility and fees must be checked against official sources at setup time.

## Current status

This is the treasury target specification. Existing OpenCompany finance is an internal ledger and owner-attested recordkeeping. No live bank, processor, or wallet is currently connected by this specification.
