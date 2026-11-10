# OpenCompany worker runner

## Runtime contract

`OpenCompanyWorker.run_once(agent_id, role_key)` claims at most one durable
queue lease, reloads the work item from the authoritative store, verifies the
assigned agent and `in_progress` state, and invokes the existing cost-gated
specialist executor. The result must be written through an injected durable
`ArtifactSink`; the worker fails closed if no sink is configured. It records
an audit event and completes the lease only after the sink confirms persistence.

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
the exception for process-level logging/alerting. Error details stored in the
queue/audit contain exception types, not potentially sensitive exception text.
