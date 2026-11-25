# Worker and task lifecycle reliability audit — 2026-11-25

## Scope
Read-only source inspection of the clean-room worker and task queue in `opencompany_v2`. No runtime changes made.

## Findings

### W-01 — Queue acknowledgement and task state/result updates are not atomic
**Evidence:** `AgentWorker.run_once()` calls `TaskService.record_result()`, then queue `complete()`, then transitions the task to its terminal status. These writes occur in separate operations.
**Risk:** A crash or lease loss between steps can leave an execution result stored on a RUNNING task while the queue is not completed, or a queue job completed while the task status remains RUNNING. A retry/re-delivery may then repeat the handler.
**Recommendation:** Add an execution-finalization transaction or explicit idempotent completion protocol. Persist execution ID, attempt number, and result identity; revalidate lease ownership at the point of committing the task result and terminal queue state. Where a shared DB is used, make finalization atomic.

### W-02 — Handler side effects occur before the queue completion check
**Evidence:** The worker calls the skill handler, validates and records its result, and only afterward calls `queue.complete()`.
**Risk:** A handler with side effects could act, but its acknowledgement could fail because the lease expired or was lost. At-least-once queue semantics means duplicate execution is possible.
**Recommendation:** Do not claim exactly-once effects. Require idempotency keys for external provider calls, approval records bound to the task/action/recipient, and an outbox or provider idempotency strategy for any future effect. For read-only research, accept retry duplicates but deduplicate persisted artifacts.

### W-03 — `TaskService.move()` is not visibly serialized with concurrent task updates
**Evidence:** The method reads a task from `list_tasks()`, validates a transition, mutates the record, and updates the database. Unlike nearby assignment/result/progress methods, the operation does not visibly wrap its read-transition-write sequence in the store lock.
**Risk:** Concurrent state transitions may both validate against stale state or overwrite one another.
**Recommendation:** Wrap transition validation and write in a single lock/transaction; use conditional update against the expected current status and require one row updated.

### W-04 — Queue uniqueness permanently binds one job to each task ID
**Evidence:** `execution_jobs` has `UNIQUE(task_id)`; `enqueue()` returns an existing job ID regardless of its state.
**Risk:** A task that has completed, exhausted retries, or has a dead-letter job cannot create a new job using the same task ID. This limits intentional re-execution/revision unless a new task ID or explicit requeue operation is used.
**Recommendation:** Add a controlled retry/requeue operation that records the previous job, new attempt/revision, actor, and reason. Keep accidental duplicate enqueue idempotent.

### W-05 — General worker and agent worker use different queue-claim scopes
**Evidence:** `Worker.run_once()` calls `claim(worker_id, lease_seconds)` without an agent ID; `ExecutionQueue.claim()` then filters to payloads whose `agent_id` is null. `AgentWorker` claims jobs with its explicit agent ID.
**Assessment:** This separation is intentional and protects agent assignment. Preserve it and add regression tests for mismatched identities and unassigned jobs.

## Verified strengths
- Queue claims use an immediate SQLite transaction.
- Agent-scoped queue claims filter jobs by the assigned agent.
- Worker validates task/agent identity, persisted skill assignment and skill version, and current capability requirements before invoking the handler.
- Sensitive skill approval is resolved by trusted server-side code, not payload boolean.
- The queue documentation correctly warns that execution is at-least-once and handlers must be idempotent.

## Recommended implementation order
1. Make task transition read/validate/write atomic with conditional status update.
2. Make result and terminal task status updates lease-aware and idempotent.
3. Add explicit execution-attempt and idempotency-key records; cover lease-loss and crash-window tests.
4. Add controlled requeue for dead/completed tasks with auditable reason and owner/CEO policy.
5. Keep external side-effect adapters disabled until communication approval and idempotency are enforced end-to-end.

## Approval boundary
Audit only. No changes to financial logic, worker runtime, permissions, queue semantics, external integrations, or deployment.
