## Bounded worker queue, runner, and supervisor

The independent worker queue provides durable SQLite-backed enqueue/claim/complete/fail operations, atomic lease acquisition, stale-token rejection, expired-lease recovery, and a configurable retry ceiling with a dead-letter state. Payload size, retry count, and lease duration are bounded.

OpenCompanyWorker connects a queue lease to the independently authored specialist executor. Before execution it reloads the work item and verifies the assigned agent and in_progress state. The worker requires an injected durable artifact sink, records a hash-chain audit event, and acknowledges the queue only after the deliverable is saved. Outputs remain review-required.

Artifact IDs are deterministic for a given work-item/role pair. A retry after a crash between artifact persistence and queue acknowledgement therefore reuses the same idempotency key; the sink must enforce uniqueness/upsert semantics on that key. Request budgets must be finite and non-negative. Provider ceilings and provider-reported costs are also checked for finite, non-negative values. No model providers are enabled by default.

WorkerSupervisor supplies a foreground polling loop with graceful stop-event handling, bounded polling/backoff intervals, and a consecutive-failure circuit breaker. It does not daemonize or install process signal handlers; a container/process manager must own process lifecycle and deliver shutdown through the stop event. The optional cycle limit is intended for bounded runs and tests.

This is not yet a production worker deployment. A production artifact store, supervised deployment configuration, persistent volume/backup strategy, owner dashboard, production authentication, monitoring, and integration tests against the target deployment remain release requirements. The supervisor itself grants no shell, browser, external integration, or protected-action authority.

Queue admission also verifies that every prerequisite belongs to the same business unit as the task. A dependency from another business is rejected even if it is completed.

## Owner-reviewed re-admission

A work item has one durable queue row across its lifecycle. After the owner rejects a review draft and returns the item to READY, or transitions a dead-lettered FAILED item back to READY, the same queue row may be reused. Re-admission resets the exhausted attempt counter and clears the previous lease/error fields. It is permitted only when the prior queue row is terminal (done or dead); an existing queued or leased row cannot be overwritten. The task-state change, queue re-admission, delegated-child state check, and owner audit event remain inside the same transaction.

This supports controlled revision and retry without creating duplicate queue rows or bypassing the owner-controlled READY/approval gate. A completed work item remains terminal and cannot be re-admitted.

## Restart-safe internal automation scheduler

The opt-in runtime now uses `DurableAutomationScheduler` for periodic internal maintenance. Job identity, interval, enabled state, next due time, execution status, failure count, and lease expiry are stored in the same SQLite database as the company runtime. The fleet polls the scheduler; it does not create a second background process.

A due job is claimed transactionally before its callback runs. A process crash leaves a lease that expires, after which a restarted process can reclaim the overdue job. Successful runs schedule the next interval from completion. Failed runs record only the exception type and use bounded exponential backoff. Callback payloads and exception messages are not persisted.

This provides at-least-once scheduling, not exactly-once side effects. Every callback must be idempotent because a crash can occur after a callback's work but before its completion is recorded. The scheduler is not a permission system: external actions remain subject to the existing owner-approval controls. It is inert unless the corresponding automation is explicitly enabled and the owner starts the verified worker fleet. The default Product & R&D automation setting remains disabled.
