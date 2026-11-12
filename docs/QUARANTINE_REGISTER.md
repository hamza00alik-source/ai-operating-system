# Legacy Quarantine and Provenance Register

**Applies to:** the independent OpenCompany implementation, including `feature/opencompany-aios-unification`.  
**Status:** active; quarantine is in place, but full provenance and release reviews remain open.

## Product boundary

The current product is OpenCompany AIOS. The independent runtime is implemented in:

- `src/opencompany_app/` — FastAPI application, runtime composition and owner console.
- `src/opencompany_core/` — domain services, orchestration, persistence, model gateway and business logic.

The legacy `src/ai_os/` package is not the new runtime and must not be imported by OpenCompany. Historical files may remain in Git for traceability, but must be excluded from production build context and package/runtime entrypoints.

## Quarantined material

| Path or area | Reason | Required treatment |
|---|---|---|
| `src/ai_os/` | Legacy implementation; separate runtime and historical code | Keep out of OpenCompany imports, package artifacts and Docker image |
| `data/agency_agents_manifest.json` | Third-party Agency Agents role catalogue | Historical/provenance reference only; exclude from runtime/build context |
| `data/repository_sources.json` | External project/source inventory | Provenance record only; must not drive runtime loading or code generation |
| Legacy tests importing `ai_os` | Validate the legacy implementation, not the independent runtime | Keep separate from OpenCompany acceptance suite |
| Old Agency Agents documentation and prompts | Third-party reference material | Do not present as OpenCompany-authored role playbooks or capabilities |

`data/company_departments.json` must be treated as legacy/reference data unless a current OpenCompany module explicitly owns and validates its use. Do not assume it is a source of truth for the new company structure.

## Independent implementation facts

- The OpenCompany runtime has its own application composition, persistence, owner authentication/session controls, audit records, worker queue, deliverable review and model gateway.
- The current role catalogue contains 500 specialist role contracts, ten manager roles and one executive orchestrator: 511 contracts total. These are not 511 continuously running agents.
- Specialist procedures are generated from a shared playbook template and role-specific title/mission/capability data. They are differentiated role contracts, not 500 separately authored expert manuals.
- Four business-unit scopes are represented: core, physical-products agency, own physical-product brand and digital products. Continue enforcing unit-level isolation for records, work, credentials and external integrations.
- Agency Agents and Teamily AI may be consulted for selective ideas only. Neither is the architecture or codebase to copy; OpenCompany must remain independently designed and owned.

## Audit evidence and limits (2026-11-12)

- The inspected repository tree contained 161 tracked files.
- Exact whole-file hash comparison found zero duplicate-file groups in the inspected tree.
- A direct-reference scan of all 42 Python files under `src/opencompany_app` and `src/opencompany_core` found no direct imports or textual references matching the scanned Agency Agents identifiers/URLs or legacy `ai_os` import patterns.
- Eleven legacy test modules still import `ai_os`: `test_agent_runtime.py`, `test_api.py`, `test_brain.py`, `test_business_ops.py`, `test_credentials.py`, `test_owner_session_auth.py`, `test_provider_failover.py`, `test_research_sources.py`, `test_sessions_and_workforce.py`, `test_website_api.py` and `test_workflows.py`.
- The audit also found outdated documentation and an old `AI_OS_...` environment template, which this cleanup is intended to correct.
- This is not a semantic similarity, function-level duplication, AST clone-detection or legal provenance review. Zero whole-file duplicates and zero direct references do not prove that every function is original or that all licensing obligations have been satisfied.
- Tests were not executed. The owner has deferred CI/testing until 2026-12-01; do not report test pass status.

## Build and packaging rules

The Docker build must exclude at least:

- `src/ai_os/`
- `data/agency_agents_manifest.json`
- `data/repository_sources.json`
- `tests/`, local virtual environments, Git metadata, caches and local secret files

Keep the historical source and provenance evidence in Git where useful; excluding it from the image does not mean deleting the historical record. Review every future Docker build-context change to ensure the legacy runtime does not re-enter the production image.

## Remaining release and independence work

1. Complete function-level/AST and semantic similarity review, plus a human provenance/licensing review.
2. Review direct and transitive dependencies and produce a software bill of materials.
3. Ensure legacy tests are isolated and create/maintain independent OpenCompany acceptance coverage after the testing deferral ends.
4. Resolve the UnoRouter provider's commercial-use, privacy and account eligibility in writing before company workloads rely on it.
5. Complete security review, owner/operator permission model, secret rotation and session recovery guidance.
6. Complete workflow cancellation/resume, failure diagnostics, multi-host coordination and controlled knowledge access/retention.
7. Complete external integrations individually with business-unit isolation and owner approval boundaries.
8. Establish encrypted off-host backups, restore rehearsal, monitoring and incident runbooks.
9. Complete mobile-browser and production acceptance, followed by a separate owner-approved staging/cutover/rollback plan.
10. Obtain qualified legal review before commercial distribution.

## Explicit non-authorization

This register does not authorize merging branches, deploying, changing `vercel.json`, modifying production routing or data, running tests before the deferred date, spending money, enabling paid inference, publishing, contacting customers or taking financial actions.
