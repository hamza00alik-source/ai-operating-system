# Delegation approval and task materialization

A manager proposal is not executable work. The owner-controlled approval
endpoint is a separate step:

`POST /work-items/{parent_id}/delegation-proposals/{proposal_id}/approve`

Before approval, the API verifies:
- the proposal belongs to the supplied parent work item and is still a draft;
- the plan has no unresolved capability gaps;
- every selected agent profile still exists and is explicitly ACTIVE;
- the assigned role, team and department still match the saved proposal.

Approval atomically writes the child work items, updates the proposal and child
records to approved, and appends tamper-evident audit events in the same SQLite
transaction. The child work items are created in READY state and retain their
assigned agent IDs. The original child-task identifiers are reused.

**Approval does not enqueue or execute work.** No model call, worker start,
external action or paid usage occurs. Queue admission is a later, separate
owner-controlled stage. The API reports `queue_entries_created=false` and
`execution_started=false`.

A proposal with unresolved capabilities cannot be approved. A specialist or
manager profile must first be activated through the owner-authenticated agent
state endpoint. The approval operation is idempotently guarded by the proposal
status: only a draft proposal can be approved, and a concurrent or repeated
approval receives a conflict response.

The materialization and audit writes are transactional. If the child set does
not exactly match the persisted proposal, no task or approval status is saved.
