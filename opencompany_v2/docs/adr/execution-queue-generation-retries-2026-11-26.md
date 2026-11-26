# ADR: Execution Queue Re-enqueue Semantics

**Status:** Proposed  
**Date:** 2026-11-26  
**Scope:** `opencompany_v2` durable execution queue

## Context

The current `execution_jobs` table has a `UNIQUE(task_id)` constraint. `ExecutionQueue.enqueue()` returns the existing job ID for a task regardless of whether that job is queued, leased, completed, or dead. This protects against duplicate initial submissions, but it also prevents a task from being deliberately retried after a terminal queue state. Resetting the existing row would erase execution history and can make result-recovery logic confuse a prior execution with a new one.

## Decision direction

A deliberate re-run must create a distinct execution identity while retaining the task identity and all earlier job records. Do not reset or recycle a completed/dead job row.

The preferred design is an execution-generation model:
- Keep `task_id` as the logical task reference; remove the table-wide uniqueness constraint on it through a SQLite table rebuild migration.
- Add a per-task `generation` integer and enforce `UNIQUE(task_id, generation)`.
- Keep the original enqueue API idempotent for the same generation. A caller must explicitly request the next generation to re-run a task; no automatic requeue of completed jobs.
- Store the generation in the task payload and task result identity so reconciliation can only match the correct job.
- Re-enqueue only when the task lifecycle and owner/CEO policy explicitly permit it. The initial safe policy should allow requeue only from terminal states after the task has been reset to READY through a valid lifecycle transition.
- Preserve previous job rows, results, errors, attempts, and timestamps for audit.
- Ensure agent assignment, skill key/version, and approval resolver checks are revalidated on every generation.
- Reject re-enqueue when a task still has a queued or leased job, or when a generation is already queued/leased.

## Migration and safety requirements

1. SQLite migration must rebuild the table transactionally and preserve all existing rows and IDs.
2. Migration must be idempotent and tested against both a fresh database and a legacy database with existing jobs.
3. The queue must never claim an older completed/dead generation when a newer generation is queued.
4. Task-result reconciliation must match both task ID and job ID; a result from generation N must never complete generation N+1.
5. Tests must cover duplicate enqueue for one generation, explicit generation advance, concurrent enqueue, legacy migration preservation, active-job rejection, and stale-generation result isolation.
6. The API/owner dashboard must expose explicit retry/re-run semantics before enabling owner-facing actions.

## Non-goals

- No exactly-once claim: handler side effects can still occur more than once after crashes. External handlers must remain idempotent or require approval.
- No autonomous external sending, publishing, payments, or spending.
- No change to finance evidence or revenue-recognition semantics.
- No merge, deployment, or live operation change in this ADR.

## Rollout

Implement the migration and queue API behind tests first. Keep explicit generation retry unavailable to production callers until migration tests, queue tests, task-service reconciliation tests, and CI are green.
