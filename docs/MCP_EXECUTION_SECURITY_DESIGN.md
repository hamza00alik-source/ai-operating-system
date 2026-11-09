# MCP execution security design (not enabled)

## Status

This document defines the next execution milestone. It does not enable MCP tool calls.
The current runtime remains fail-closed: `call_mcp_tool(...)` raises before loading
credentials or opening a network connection. Proposal approval and reservation are
audit checkpoints only.

## Required execution architecture

The API process must never execute untrusted MCP tools inline. A future executor must
be a separately deployed worker with its own identity, resource limits and explicit
network policy. It must not inherit the Owner Console's broad environment.

### Trust boundaries

1. **Agent runtime** — may create a proposal from a fixed department allowlist. It
   cannot access credentials or the MCP network.
2. **Owner Console/API** — authenticates the owner, displays exact arguments and
   records one-time approve/reject decisions. A separate confirmation reserves an
   approved low-risk proposal.
3. **Execution broker** — future component that atomically claims a valid reservation.
   It must re-check the proposal fingerprint, schema digest, expiry, enabled server,
   department grant and risk classification immediately before dispatch.
4. **Isolated worker** — future component that performs one bounded call. It must
   receive only the single server credential and endpoint required for that call.
5. **Result recorder** — persists a bounded, sanitized result and immutable audit
   events. Agent resumption is a separate, controlled transition.

## Required state machine

```text
pending -> approved -> reserved -> queued -> running -> succeeded
    |          |          |          |          |-----> failed
    |          |          |          |          |-----> timed_out
    |          |          |          |          |-----> cancelled
    |          |          |          |-----> cancelled
    |          |          |-----> expired / invalidated
    |          |-----> rejected
    |-----> expired
```

- Every transition must be conditional and transactional.
- A reservation and execution claim must each be one-time and replay-resistant.
- A crash after claim must not silently replay an external side effect.
- Retry requires a new owner-reviewed proposal unless the tool is proven idempotent
  and a separate retry policy is approved.
- The current reservation record is not an execution claim and cannot be consumed
  by an executor yet.

## Mandatory worker limits

Before any network execution is enabled, implement and test:

- A separate OS/container boundary; no shell or arbitrary code supplied by the model.
- Fixed executable and fixed protocol implementation; no dynamic package installation.
- CPU, memory, process-count, wall-clock and response-byte limits.
- Per-server outbound network allowlisting, DNS/IP pinning and TLS hostname checks.
- No redirects, proxy inheritance, private/link-local/loopback destinations or
  metadata-service access.
- Per-call credential injection only after all authorization checks; secrets must
  never be written to logs, prompts, database rows or result payloads.
- Strict JSON input/output validation, redaction and bounded result persistence.
- Cancellation, worker termination, timeout handling and crash recovery.
- Immutable audit events for claim, start, completion, failure and cancellation.

## Agent resumption

The agent must remain paused after approval and reservation. A future result recorder
may resume it only after a successful, verified result has been committed. Failed,
timed-out, cancelled, invalidated or ambiguous calls must remain paused for owner
review. No automatic retry of uncertain external effects.

## Release gates

Remote execution stays disabled until all of the following are true:

1. The isolated worker and broker are implemented independently of the API process.
2. Security tests cover replay, races, schema drift, disabled servers, allowlist
   revocation, expired approvals, credential isolation, SSRF, output limits and
   crash recovery.
3. The complete test suite passes on the exact reviewed commit.
4. The owner reviews the threat model and explicitly authorizes a separate release.
5. Deployment capacity is available and the owner separately authorizes deployment.

No part of this design authorizes publishing, messaging, payments, account changes,
or other external commitments. Those require separate risk policies and approvals.
