# Finance evidence gap audit — 2026-11-25

## Scope

Read-only audit of the existing OpenCompany finance and treasury implementation on `opencompany-merged-clean`. This note records verified code-level findings. It does not change financial behavior, create transactions, connect payment rails, or authorize spending.

## Findings

### F-01 — Revenue entries are owner-entered classifications, not verified receipts

**Evidence**
- `src/opencompany_app/api.py`, `POST /finance/entries`: accepts `entry_type="revenue"` when an owner-authenticated request supplies `confirm_owner_record=true`.
- `src/opencompany_app/runtime.py`, `FinanceRepository.create_entry`: stores amount, currency, description, business unit, and timestamp. It has no order reference, payment-provider transaction ID, bank-statement artifact, receipt hash, or verification-source field.
- `FinanceRepository.budget_status`: sums every `entry_type='revenue'` row into `revenue_minor` and computes `net_minor`; it does not filter on review status.
- `POST /finance/entries/{entry_id}/review` permits `owner_verified`, but the review stores only an action and rationale. It does not require evidence or independent verification.

**Impact**
A manually entered revenue row can appear in the finance status as revenue and contribute to the displayed net figure even if it has no payment evidence and has not been reviewed. An owner review label is not independent payment verification.

**Required correction before financial use**
Separate at least these states and totals:
1. Internal order value (never cash received).
2. Payment claim / owner-attested receipt (evidence reference supplied by owner; not independently verified).
3. Independently verified receipt (only when a trusted payment or bank source actually confirms it).
4. Fees, refunds, chargebacks, and expenses as separate records.

Only state 3 should contribute to a metric labelled confirmed cash receipts. Do not calculate profit until all relevant costs, fees, refunds, and timing rules are represented.

### F-02 — Reconciliation is arithmetic over owner-supplied figures

**Evidence**
- `POST /finance/reconciliations` accepts owner-supplied opening and statement-closing balances.
- The reconciliation compares those values with movement calculated from the internal finance entries.
- The API response explicitly reports `bank_connection_attempted=false`; there is no bank statement ingestion or independent bank-source verification in this path.

**Impact**
A result of `balanced` means the entered numbers reconcile arithmetically. It does not establish that the statement is authentic or that the funds exist in an account.

**Required correction before financial use**
Keep the status named as owner-entered/manual reconciliation unless a supported bank statement source or provider connection is independently verified. Preserve statement provenance and evidence references.

### F-03 — Treasury accounts and journal are offline records

**Evidence**
- `src/opencompany_core/treasury.py` describes the repository as offline and states no payment rails are connected.
- Treasury account records are created with `status="record_only"`.
- The account listing reports `live_provider_balance_available=false`.
- Journal posting validates balanced debit/credit entries but returns `funds_moved=false`.

**Impact**
An account or balanced journal entry is an internal record, not a live account balance or proof of a transfer.

## Safe current labels

- Sales pipeline: internal orders, not revenue.
- Finance revenue rows: owner-entered revenue claims, not independently verified receipts.
- Owner review: owner review/attestation, not external verification.
- Reconciliation: manual arithmetic reconciliation unless supported source evidence is attached and validated.
- Treasury accounts/journal: record-only; no live balance or money movement.

## Approval boundary

The next implementation step changes financial semantics and reporting. It must not be made silently. Before changing existing finance calculations or adding receipt-ledger behavior, obtain explicit owner approval for the financial-model change. Do not merge or deploy as part of this audit.

## Verification performed

- Inspected `FinanceRepository` schema and methods in `src/opencompany_app/runtime.py`.
- Inspected finance entry, review, budget-status, and reconciliation routes in `src/opencompany_app/api.py`.
- Inspected `TreasuryRepository` in `src/opencompany_core/treasury.py`.
- Confirmed the latest preceding application commit's reported CI checks separately; this documentation-only audit has not yet been tested by CI.
