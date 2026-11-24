# OpenCompany — Clean Rebuild

This directory contains a ground-up implementation of OpenCompany. It is original project code and architecture. It does not import, copy, or depend on another AI-company repository.

## Principles
- Owner-owned architecture and source.
- Free-first operation; no paid resources by default.
- Evidence before opportunity claims.
- Autonomous execution only within explicit capability boundaries.
- Owner approval for publishing, spending, customer commitments, refunds, production changes, and sensitive operations.
- Research and task completion never count as revenue.
- Secrets stay outside the repository.

## Implemented foundation
- Domain entities, task lifecycle validation, and task service.
- SQLite persistence and append-only hash-linked event ledger.
- Transparent opportunity scoring.
- Fail-closed owner approval policy.
- Agent profile/result contracts and approval-gated persistent brain memories.
- Product draft/review workflow and channel-readiness checks.
- Durable SQLite execution queue with idempotent enqueue, worker leases, heartbeat, retries, and dead-letter state.
- Bounded worker dispatch through explicitly registered handlers.

## Execution semantics
The queue provides at-least-once delivery, not exactly-once side effects. A process can crash after a handler performs work but before the job is acknowledged. Therefore handlers must be idempotent and external side effects must still pass the relevant owner-approval policy. Leases are not a substitute for approval or security controls.

## Run
Requires Python 3.11+.

```bash
cd opencompany_v2
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m opencompany
python -m unittest discover -s tests -v
```

The runtime currently uses only Python's standard library. Tests are committed but have not yet been executed in a connected Python environment.
