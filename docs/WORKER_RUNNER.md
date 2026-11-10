# OpenCompany worker runner

## Runtime contract

`OpenCompanyWorker.run_once(agent_id, role_key)` claims at most one durable
queue lease, reloads the work item from the authoritative store, verifies the
assigned agent, active profile state, persisted role identity, matching department and team,
and `in_progress` state, and invokes the existing cost-gated
specialist executor. The result is first written through the injected `ArtifactSink`, then stored
in the core SQLite database with an atomic `IN_PROGRESS` → `REVIEW` transition
and audit event. The core store retains the full draft content, provider/model
provenance, cost, role and review-required flag. The owner API exposes these
records through `GET /work-items/{id}/deliverables`. The sink remains mandatory
as a secondary durable artifact destination.

All generated deliverables are review-required drafts. The worker has no
shell, browser, publishing, payment, customer-messaging, credential, or
deployment tools. Model providers remain disabled unless explicitly configured.
A paid provider still requires a positive per-request budget and a matching
owner-approved provider policy. The default request budget is zero.

## Operating it

A host process may call `run_once` in a bounded loop, with one worker instance
per process and a configured concurrency limit at the supervisor level. Use
graceful shutdown between calls. The queue lease recovers abandoned work after
expiry; retries are bounded by the queue's configured maximum attempts.

This module deliberately does not start a background process at API import
time. Deployment must supply a durable artifact sink, persistent storage,
worker supervision, health monitoring, backup/restore procedures, and an
approved model adapter. These are deployment responsibilities and are not
enabled by this commit.

## Failure semantics

Execution or artifact persistence failures mark the lease failed (retrying
until the queue's attempt limit), append a failure audit event, and propagate
the exception for process-level logging/alerting. Once the queue dead-letters
a task, the core store atomically moves its still-in-progress work item to
`FAILED` with audit evidence. If a process crashes after the core draft and
`REVIEW` transition commit but before queue acknowledgement, a later worker
recognizes the already-saved role deliverable and acknowledges the lease
without invoking the model again. Error details stored in the
queue/audit contain exception types, not potentially sensitive exception text.


Agent profiles persist a `role_key` and `team_key`. Owner-authenticated state changes use optimistic revision checks and append an audit event atomically. A profile must be explicitly activated by the owner before the worker will execute it. Activation does not start a worker, enqueue work, or trigger model usage.
