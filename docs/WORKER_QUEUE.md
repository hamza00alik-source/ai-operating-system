## Bounded worker queue, runner, and supervisor

The independent worker queue provides durable SQLite-backed enqueue/claim/complete/fail operations, atomic lease acquisition, stale-token rejection, expired-lease recovery, and a configurable retry ceiling with a dead-letter state. Payload size, retry count, and lease duration are bounded.

OpenCompanyWorker connects a queue lease to the independently authored specialist executor. Before execution it reloads the work item and verifies the assigned agent and in_progress state. The worker requires an injected durable artifact sink, records a hash-chain audit event, and acknowledges the queue only after the deliverable is saved. Outputs remain review-required.

Artifact IDs are deterministic for a given work-item/role pair. A retry after a crash between artifact persistence and queue acknowledgement therefore reuses the same idempotency key; the sink must enforce uniqueness/upsert semantics on that key. Request budgets must be finite and non-negative. Provider ceilings and provider-reported costs are also checked for finite, non-negative values. No model providers are enabled by default.

WorkerSupervisor supplies a foreground polling loop with graceful stop-event handling, bounded polling/backoff intervals, and a consecutive-failure circuit breaker. It does not daemonize or install process signal handlers; a container/process manager must own process lifecycle and deliver shutdown through the stop event. The optional cycle limit is intended for bounded runs and tests.

This is not yet a production worker deployment. A production artifact store, supervised deployment configuration, persistent volume/backup strategy, owner dashboard, production authentication, monitoring, and integration tests against the target deployment remain release requirements. The supervisor itself grants no shell, browser, external integration, or protected-action authority.
