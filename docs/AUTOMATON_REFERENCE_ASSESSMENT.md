# Automaton Reference Assessment

Reviewed repository: [hamza00alik-source/automaton](https://github.com/hamza00alik-source/automaton), a fork of [Conway-Research/automaton](https://github.com/Conway-Research/automaton).

License: MIT. Any copied or adapted substantial source must retain the upstream copyright and license notice. This assessment records design patterns; it does not copy the Automaton runtime.

## Executive decision

Use Automaton as a **secondary architecture reference**, not as the base runtime and not as a dependency. Agency Agents remains the primary source for specialist roles and team workflows. AI Operating System remains the owner-controlled, free-first runtime.

Automaton is technically rich, but its default operating model is incompatible with this project's zero-budget requirement: it is designed around Conway compute credits, Conway inference, a wallet/USDC survival model, and optional paid provider keys. Its documentation describes paid compute funding and automatic top-ups. The source also includes an Ollama backend, but local inference does not make Conway sandbox operations, wallet features, or all orchestration paths free.

## Useful patterns to adapt selectively

| Automaton subsystem | Useful design idea | AI Operating System adaptation |
|---|---|---|
| ReAct agent loop | Think → act → observe → persist | Add a bounded worker lifecycle with explicit step records |
| Durable heartbeat scheduler | DB-backed schedules, leases, timeouts, retries | Add local SQLite scheduler; no hosted service required |
| Orchestrator and task graph | Dependency-aware plans, retries, blocked states | Add a DAG planner and deterministic task state machine |
| Local worker pool | In-process specialist workers | Prefer one local process first; no paid child sandboxes |
| Model registry/router | Provider-neutral model metadata and routing | Add a free-only allowlist and explicit zero-cost guard |
| Inference budget tracker | Per-call/session/hour/day accounting | Keep spend tracking; default allowed model cost must be exactly zero |
| Five-tier memory | Working, episodic, semantic, procedural, relationship memory | Add progressively, with user-data minimization and deletion controls |
| Policy engine | Central tool-call authorization point | Require server-side policy enforcement before every tool call |
| Prompt-injection defenses | Treat external content and skills as untrusted | Adapt with tests; sanitization alone is not authorization |
| Audit/versioned changes | Record changes and preserve rollback history | Use proposed patches and human approval; no self-editing production code |

## Features explicitly excluded from the zero-budget OS

- Conway Cloud provisioning and paid sandbox usage.
- Conway inference credits and automatic credit top-ups.
- Wallet generation for business operations, USDC transfers, x402 payments, domain purchases, or autonomous treasury activity.
- Automatic spending, paid fallback, or subscription creation.
- Self-replication and funded child agents.
- Unrestricted shell access, root-level execution, or automatic production self-modification.
- Unreviewed installation of npm packages, MCP servers, or remote skills.

These exclusions are intentional product requirements, not missing implementation tasks.

## Free/local inference finding

Automaton's source contains an Ollama backend and can discover local Ollama models when an Ollama base URL is configured. This is a useful adapter pattern. However, its standard setup and broader runtime are still Conway-oriented, and its docs describe API provisioning and paid inference. We must isolate the local model adapter from Conway identity, billing, and sandbox modules.

A local model has no per-token API charge, but it still needs compatible hardware, storage, electricity, and a continuously running host. An Android-only phone may not be a practical always-on host for a capable multi-agent model. Do not claim unattended execution until an actual zero-cost host is identified and tested.

## Required safeguards before adapting patterns

1. Keep paid providers disabled and reject non-zero model pricing in free-only mode.
2. Do not silently fall back from local inference to a hosted provider.
3. Put all tool execution behind a server-side permission gate.
4. Default external actions, publishing, purchases, financial transfers, and customer commitments to denied pending owner approval.
5. Do not expose shell, filesystem, wallet, or deployment tools to an LLM by default.
6. Make scheduler jobs idempotent, bounded by timeouts, and observable.
7. Treat retrieved webpages, emails, files, and agent skills as untrusted data.
8. Store secrets outside Git; never include secrets in prompts, logs, or agent packets.
9. Keep agent memory scoped, inspectable, and deletable.
10. Require review, tests, and rollback for every code change; no autonomous production self-modification.

## Implementation order

1. Add durable task state and dependency graph to the existing SQLite runtime.
2. Add a bounded local worker queue that can create and return manual/free-chat work packets.
3. Add scheduler/leases/retries without requiring a model.
4. Add a local inference interface with Ollama as an optional adapter, strictly local URL only.
5. Add policy enforcement and audit records before connecting any tools.
6. Add memory/evaluation after the above foundations are tested.

## Source files inspected

- `README.md`, `package.json`, `LICENSE`, `ARCHITECTURE.md`, `DOCUMENTATION.md`
- `src/agent/loop.ts`, `src/agent/policy-engine.ts`, `src/agent/injection-defense.ts`
- `src/inference/router.ts`, `src/inference/registry.ts`, `src/inference/budget.ts`, `src/inference/types.ts`
- `src/conway/inference.ts`, `src/heartbeat/scheduler.ts`, `src/memory/retrieval.ts`, `src/agent/spend-tracker.ts`, `src/config.ts`

This is a source-level design review, not a security audit or a successful build/test claim.
