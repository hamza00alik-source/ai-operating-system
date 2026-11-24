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

## First milestone
A small, testable core: durable task ledger, auditable events, opportunity scoring, and explicit workflow states.

## Run
Requires Python 3.11+.

```bash
cd opencompany_v2
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m opencompany
```

The first version uses only Python's standard library at runtime.
