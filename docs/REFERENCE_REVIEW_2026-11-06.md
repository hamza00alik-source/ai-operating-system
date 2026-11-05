# Reference repository review — 2026-11-06

Reviewed the latest repository metadata, recent commits, and relevant file trees for all ten pinned references. These repositories remain references only; no reference repository was modified.

## Results

| # | Repository | Latest visible commit / push | Finding | Decision |
|---|---|---|---|---|
| 1 | [blueprint-ai-first-company](https://github.com/saurav-yirifi/blueprint-ai-first-company) | Latest commit 2026-08-14; pushed 2026-09-27 | Detailed research/writing pipeline, voice consistency, source/citation management, editorial review, lessons learned, link-check workflow | Adopt the general idea of source provenance, staged review, and quality checks where relevant. It is a knowledge/workflow blueprint, not an execution runtime. |
| 2 | [ai-company](https://github.com/itsPremkumar/ai-company) | Latest commit 2026-07-13; pushed 2026-07-14 | Broad department catalog, integration map, rollout roadmap, explicit infrastructure and model cost breakdown | Use department coverage and honest cost accounting as planning references. Its documented stack has substantial paid infrastructure/API costs and is not our zero-budget baseline. |
| 3 | [ai-company-agent-platform](https://github.com/RagaviDevX/ai-company-agent-platform) | Latest commit 2026-09-07 | JWT primitives, opt-in auth gate, middleware, memory/RAG, Docker hardening, non-root container, CI with Ruff and pytest | Relevant security and CI reference. We implemented a smaller single-owner token gate and audit middleware; do not copy its full stack or add JWT dependency yet. |
| 4 | [ai-tech-team-company-live](https://github.com/bdno1agency/ai-tech-team-company-live) | Initial commit 2026-10-07 | Repository currently contains only a README | No implementation change to adopt. Recheck if code is added. |
| 5 | [one-person-ai-company-starter](https://github.com/psorii/one-person-ai-company-starter) | Latest commit 2026-10-31 | Fresh free starter and a practical pre-release checklist covering claims, recipient, price consistency, refunds, listing files, payment link, deploy/tests/rollback | Adopt pre-publish and pre-release checklist principles. These become mandatory approval gates before any external action. |
| 6 | [ai-automation-company-setup](https://github.com/paulswarna794-boop/ai-automation-company-setup) | Initial commit 2026-09-12 | Repository currently contains only a README | No implementation change to adopt. |
| 7 | [claude-code-ai-company](https://github.com/qaptanjes/claude-code-ai-company) | Latest commit 2026-08-08 | Specialist role library and memory folders, but designed around Claude Code | Do not adopt provider-specific runtime or Claude dependency, per owner requirement. General role/memory organization is already covered by our Agency Agents-first approach. |
| 8 | [verified-ai-labor](https://github.com/StellarRequiem/verified-ai-labor) | Initial release 2026-06-06 | Deterministic stub daemon, human-gated stages, fail-closed claim gate, append-only SHA-256 hash-chained event log, tests | Strong design reference. We adopted the standard-library hash-chain concept for our SQLite audit log. Do not copy its live model path or assume its gate verifies arbitrary factual claims without its verifier dependency. |
| 9 | [MavadoClaw-Worker001](https://github.com/complianceguardaireports-wq/MavadoClaw-Worker001) | Latest commit 2026-07-09 | Approval loop, scheduled workflows, free-cascade router, local Ollama option, multiple remote providers and bridges | Approval and scheduling patterns are worth monitoring. Do not adopt the remote provider cascade: anonymous endpoints and free tiers can be rate-limited, change terms, or become unavailable, and would violate our strict no-hosted-API assumption. |
| 10 | [bmac.one](https://github.com/bmacbuilds/bmac.one) | Latest commit 2026-09-07 | README and license only | No implementation change to adopt. |

## Changes made in our OS from this review

- Added owner API token authentication, using a constant-time comparison and a 32-character minimum.
- Production mode now fails closed if the owner token is missing or too short; `/health` remains public for health checks.
- Added a SQLite append-only audit table with a SHA-256 hash chain and verification endpoint.
- Added request IDs and request metadata to audit events. Request bodies, credentials, and authorization headers are deliberately not stored.
- Added tests for auth enforcement, production fail-closed behavior, and audit-chain verification.
- Added security/operational documentation.

## Limits and next review

The audit hash chain detects modifications but is not tamper-proof if an attacker can rewrite the SQLite database and recompute all hashes. The current token gate is single-owner authentication, not full multi-role authorization or multi-user identity. Do not expose the app publicly until TLS, rate limiting, secret rotation, role-level permissions, backups, and an end-to-end security review are complete.

This is a point-in-time review of repository metadata and selected source files, not a guarantee that every commit or branch in each repository was exhaustively reviewed. Continue checking these exact ten repositories weekly and record meaningful deltas only.
