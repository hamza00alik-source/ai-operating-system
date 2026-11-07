# Hermes Agent Compatibility Evaluation

**Status:** Evaluated; integration deferred  
**Owner:** OpenCompany AI CEO  
**Constraint:** Zero spend. No installation, paid API, hosting, purchase, publication, production credential changes, or live store changes.

## Executive decision

Hermes Agent is a credible candidate execution runtime for a later OpenCompany worker integration. It is not a replacement for the OpenCompany AI Operating System, not an AI model, and not a source of unlimited free inference.

**Decision: DO NOT INSTALL OR INTEGRATE YET.** Keep Hermes on the candidate list. First complete the AI OS orchestration, provider adapter, execution logging, authentication, and approval controls. Revisit Hermes only after a suitable always-on host and zero-cost inference route have been demonstrated.

## What was verified

- Official project: https://github.com/NousResearch/hermes-agent
- Official documentation: https://hermes-agent.nousresearch.com/docs
- Latest release checked for this evaluation: v0.23.0, dated 2026-11-05.
- v0.23.0 highlights include a unified gateway owning sessions across clients, browser-served desktop workspace, Group Chats/Bot Mode, scheduled jobs, pluggable delegation, plugins, and spend limits for paid MCP tools.
- Hermes supports an Android/Termux package for aarch64 devices, but the official Termux guide currently carries a prominent warning: **the Termux package is broken and a fix is in progress**. The same guide warns Android can suspend or terminate background Termux processes. Desktop/server installation scripts are not the Android installation path.
- The Termux package omits desktop Electron, bundled Chromium, Docker, and some desktop/computer-use capabilities. It does not provide proof of local voice or wake-word support.
- Hermes requires a configured model provider. Open-source runtime software does not mean inference is unlimited or free.

## OpenCompany compatibility

The current OpenCompany AI OS repository is an early FastAPI/SQLite foundation. Its README explicitly says external AI providers, background workers, ecommerce, and social integrations are not connected. The roadmap still marks agent registry, task assignment/dependencies, retries/timeouts/logs, background worker/scheduler, source-attributed memory, provider-neutral LLM adapter, and operational integrations incomplete.

The deployment guide describes a prospective free host profile of 512 MB RAM, one CPU core, and 1 GB storage, subject to availability. It is intended for the lightweight API and small jobs, not a heavy multi-agent runtime or local model.

### Potential fit

| Hermes capability | OpenCompany use | Decision |
|---|---|---|
| Gateway and shared sessions | Optional worker interface | Evaluate later |
| Group Chats / Bot Mode | Specialist agent coordination | Useful, but not a substitute for OS task ledger |
| Delegation | Break work into bounded subtasks | Useful after task/approval controls exist |
| Persistent memory / skills | Reusable departmental procedures | Integrate only with source attribution and access controls |
| Cron / scheduled jobs | Research and maintenance runs | Later; keep dangerous actions denied |
| Browser / terminal tools | Research and controlled operations | Isolate; do not expose store credentials |
| Plugins / MCP | Extend tools | Allowlist and audit each extension |
| Spend limits | Cost guardrails | Helpful but not a substitute for OpenCompany approvals |

## Security requirements before any integration

1. Preserve OpenCompany as the system of record for tasks, approvals, audit events, and business state.
2. Invoke Hermes only through a narrow authenticated adapter; do not expose its gateway or host tools to untrusted tasks.
3. Use explicit messaging-user allowlists / pairing; never enable allow-all access for production.
4. Keep dangerous command approval enabled. Hermes documents deny-by-default behavior for cron and unattended tasks; do not change these to auto-approve.
5. Run worker commands in a restricted container or isolated host, as supported by the deployment environment; run non-root and limit CPU, memory, disk, and network access.
6. Keep model and integration credentials outside Git and logs. Use separate least-privilege credentials; do not give a worker payment or store-admin secrets.
7. Require OpenCompany approval before publishing, customer communication, purchases, spending, refunds, production changes, or commitments.
8. Correlate every dispatch with an OpenCompany task ID; record input provenance, worker identity, status, output, errors, duration, and approval decision.
9. Test prompt-injection handling, secret filtering, cross-session isolation, timeouts, cancellation, retries, and rollback.
10. Ensure the integration can be disabled or removed without losing OpenCompany data.

## Zero-cost and hosting assessment

- Do not assume Hermes' onboarding/trial model is a permanent free inference plan.
- Do not add a paid provider, subscription, VPS, or metered service without explicit approval.
- The current Android/Termux package is explicitly marked broken by its own official guide; Android background-process limits also make it unsuitable as the company's always-on production host.
- The currently documented 512 MB / 1 CPU free hosting profile is not a suitable Hermes multi-agent host.
- Reassess only when a stable, persistent, zero-cost host and a legally/operationally suitable inference route are confirmed.

## Required implementation order

1. Complete AI OS security review and role-based authorization.
2. Implement provider-neutral model adapter with hard cost ceilings and disabled-by-default paid providers.
3. Implement agent registry, task assignment, dependency handling, timeouts, retries, cancellation, and execution logs.
4. Implement source-attributed memory and retrieval access controls.
5. Enforce centralized approval gates for all external and consequential actions.
6. Build a mock worker adapter and test dispatch/result correlation without calling a real model or external service.
7. Reassess Hermes on a supported always-on host; run one harmless, isolated proof-of-concept task.
8. Integrate only if the worker is reversible, secure, reliable, and meets the zero-spend constraint.

## Sources

- Hermes releases: https://github.com/NousResearch/hermes-agent/releases
- Official documentation: https://hermes-agent.nousresearch.com/docs
- Official Android / Termux guide: https://hermes-agent.nousresearch.com/docs/getting-started/termux
- Official security guide: https://hermes-agent.nousresearch.com/docs/user-guide/security
- OpenCompany README: ../README.md
- OpenCompany roadmap: ROADMAP.md
- OpenCompany deployment constraints: DEPLOYMENT.md
