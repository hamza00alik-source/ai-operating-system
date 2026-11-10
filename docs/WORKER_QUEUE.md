## Bounded worker queue and runner

The independent worker queue provides durable SQLite-backed enqueue/claim/complete/fail operations, atomic lease acquisition, stale-token rejection, expired-lease recovery, and a configurable retry ceiling with a dead-letter state. Payload size, retry count, and lease duration are bounded.

`OpenCompanyWorker` connects a queue lease to the independently authored specialist executor. Before execution it reloads the work item and verifies the assigned agent and `in_progress` state. The worker requires an injected durable artifact sink, records a hash-chain audit event, and acknowledges the queue only after the deliverable is saved. Outputs remain review-required.

Artifact IDs are deterministic for a given work-item/role pair. A retry after a crash between artifact persistence and queue acknowledgement therefore reuses the same idempotency key; the sink must enforce uniqueness/upsert semantics on that key. Request budgets must be finite and non-negative. The worker does not grant model providers, shell commands, browser actions, external integrations, or protected business actions any authority.

This is callable orchestration, not yet a supervised always-on worker process. A deployment supervisor, production artifact store, durable-volume/backup strategy, and live health/metrics wiring remain separate release requirements. No model providers are enabled by default.
