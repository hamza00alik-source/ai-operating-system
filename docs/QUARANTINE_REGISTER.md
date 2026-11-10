# Clean-Room Quarantine Register

**Applies to:** `clean-room-rebuild`  
**Status:** Active; release-blocking items remain  
**Rule:** Listed material must not be imported, executed, loaded at runtime, or used as implementation input by the new OpenCompany application.

## Quarantined material

| Path | Reason | Required disposition |
|---|---|---|
| `data/agency_agents_manifest.json` | Imported catalogue of third-party specialist definitions and source paths | Remove from the clean application; retain provenance evidence outside runtime/build inputs if needed |
| `src/ai_os/agent_runtime.py` | Legacy runtime fetches specialist instruction files from the Agency-Agent GitHub repository | Do not call from the new app; replace only through independent requirements-first implementation |
| `src/ai_os/api.py` workforce routes | Legacy endpoints read the imported workforce manifest and expose catalogue-derived counts | Do not use as the clean application entrypoint; independently replace required endpoints |
| `data/company_departments.json` | Department registry contains mappings to imported source-catalogue departments | Re-author from OpenCompany business needs before use by the new app |
| `data/repository_sources.json` | Inventory of external reference projects | Provenance record only; must not drive code generation, role creation, runtime loading, or dependency installation |
| Legacy workforce/runtime tests | Some tests may encode behaviour of the imported catalogue and runtime | Audit each test; write new tests from OpenCompany acceptance criteria rather than porting test code |
| Legacy README and architecture documents | Some claims describe imported workforce counts and runtime behaviour | Correct before public release; clearly distinguish legacy and clean-room capabilities |

## Clean-room implementation already added

The new standalone package is `src/opencompany_core/` and the new read-only application is `src/opencompany_app/`. They do not import the legacy `ai_os` package and do not load the quarantined manifest.

Current independently authored capabilities:
- Domain contracts for agents, work items, attempts, artifacts, approvals, and audit records.
- Dependency graph validation and work-readiness preview.
- Exact-target owner approval checks for consequential actions.
- Nine OpenCompany workforce capability specifications.
- Structured agent handoff lifecycle.
- A standalone read-only FastAPI surface for health, workforce inspection, and plan preview.

## Release blockers

1. Remove the legacy runtime's external specialist-file retrieval from any deployable entrypoint.
2. Replace imported workforce endpoints and data dependencies.
3. Audit every remaining tracked file and test for provenance.
4. Review all external dependencies and produce a software bill of materials.
5. Update deployment configuration only after the independent app has equivalent required owner controls and tests.
6. Obtain a qualified legal review before commercial distribution.

## Operational boundary

This register does not authorize merge, deployment, production database changes, migrations, paid API usage, purchases, publishing, customer contact, or financial actions.
