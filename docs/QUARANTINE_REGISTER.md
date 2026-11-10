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
- Ten original OpenCompany departments and 261 role contracts: 250 specialist titles, ten department-manager roles and one executive orchestrator.
- Domain contracts, dependency-aware planning, guarded task transitions and protected-action policy checks.
- Owner-authenticated APIs for agent draft provisioning, profile state changes, work-item creation/transitions and audit-chain verification.
- Agent profiles now persist explicit role/team identity; worker execution checks active state, assigned identity, role and department.
- Structured handoff and learning proposal contracts, plus a bounded queue, worker runner and foreground supervisor.
- A separate owner console and API; this is not read-only, but it does not yet invoke models or perform external business actions.
- The 250 specialist entries are currently generated from distinct titles with templated missions/capabilities; they are not yet 250 deeply differentiated specialist playbooks.

## Release blockers

1. Keep the legacy runtime's external specialist-file retrieval and imported catalogue out of any clean-room deployable entrypoint.
2. Finish manager-led task assignment, queue integration, durable artifacts and persisted collaboration/learning.
3. Replace the new dashboard's raw sessionStorage API key with revocable HttpOnly owner sessions.
4. Complete the source/provenance review across every remaining tracked file and test; retain the manifest only as quarantined evidence if needed.
5. Review direct and transitive dependencies and produce a software bill of materials.
6. Resolve UnoRouter business-use eligibility in writing before any company workload uses it; keep consumer personal tests isolated.
7. Update deployment configuration only after the independent app has equivalent required owner controls, secure authentication, persistence, backup/restore and end-to-end tests.
8. Obtain a qualified legal review before commercial distribution.

## Operational boundary

This register does not authorize merge, deployment, production database changes, migrations, paid API usage, purchases, publishing, customer contact, or financial actions.
