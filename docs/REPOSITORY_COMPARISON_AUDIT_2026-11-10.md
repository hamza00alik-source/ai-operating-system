# Repository-wide comparison audit — 2026-11-10

## Scope and snapshot

Reviewed the repository tree on `main` and `clean-room-rebuild`, PR #105's changed-file list and patches, the old `ai_os` application entrypoints/runtime/provider/auth modules, the new `opencompany_core` and `opencompany_app` modules, deployment configuration, documentation, and the GitHub Actions workflow definitions.

Snapshot at audit start:
- `main`: 63 tracked file paths; latest commit `cae102244a9bd63fe8bec5caeabbde88d6903651`.
- `clean-room-rebuild`: 117 tracked file paths.
- PR #105: 52 changed files, 4,890 additions, 0 deletions at the initial comparison; 114 commits ahead and 2 commits behind current `main`.
- PR is draft and unmerged. No production deployment, migration, or production database change was performed.

This is an engineering audit, not a legal opinion or a guarantee of copyright clearance.

## Executive assessment

The old AIOS is the more operationally complete application today. It has an existing FastAPI entrypoint, a task execution path, a provider gateway, an owner session system, an AI Brain, discovery workers, and a live Railway routing configuration. Its major release risk is that the workforce/runtime still depends on imported Agency-Agent definitions and remote retrieval of those role instructions.

The rebuild is a cleaner independently authored domain foundation, with original OpenCompany departments, role contracts, guarded state transitions, a planning model, SQLite records, a queue, a worker abstraction, and an independent API. It is not yet a replacement operating system: the new API does not invoke models, managers do not delegate work end-to-end, queue and worker components are not composed into a running service, and the artifact sink is only an injected interface.

**Conclusion:** keep PR #105 unmerged. Continue the independent implementation, but do not point production routing at the new app until the release blockers below are closed.

## Capability comparison

| Capability | Existing AIOS on main | Independent rebuild |
|---|---|---|
| Application entrypoint | `src/ai_os.api:app`, used by current deployment | Separate `src/opencompany_app.api:app`; not selected by deployment config |
| Organization | Legacy department mapping plus imported catalogue | Ten original OpenCompany departments |
| Workforce | 283 Agency-Agent specialist definitions across 18 source departments | 250 original specialist titles plus 10 department-manager roles and one executive orchestrator (261 role contracts) |
| Specialist depth | Imported Markdown instructions fetched at runtime | Basic role contracts; specialist mission/capability fields are currently generated from title words and shared templates, not 250 individually authored specialist playbooks |
| Task execution | Bounded single-specialist run plus CEO-style review; text-only | Executor and worker abstractions exist, but no end-to-end API assignment/queue/worker composition |
| Provider routing | Existing free-confirmed provider gateway; UnoRouter can be selected by the legacy fallback router when configured | Provider-neutral gateway and an OpenRouter free adapter; no provider is wired into the new API/runtime |
| UnoRouter | Integrated in legacy provider code; repository docs conflict on whether it is company-routable | Not integrated |
| AI Brain / memory | Existing SQLite experiences and owner-reviewed memories | Learning proposal contracts only; no persistent learning loop |
| Agent collaboration | Specialist/CEO stages; no broad team delegation | Handoff contracts only; no persistent end-to-end handoff orchestration |
| Persistence | Existing SQLite-backed business, run, credential and memory records | SQLite currently persists agent profiles, work items and audit events; queue is a separate component; artifacts/handoffs/learning are not persisted by the new store |
| Owner authentication | Server-side owner sessions with HttpOnly, Secure, SameSite=Strict cookie support | API-key header only; dashboard stores the raw owner key in `sessionStorage` |
| Research/discovery | Existing GitHub metadata discovery worker and provider catalogue sync | Not yet reimplemented in the new app |
| External integrations | Existing API-Anything integration surface and legacy business endpoints | Not connected |
| Production deployment | Vercel rewrites to the existing Railway API | Not deployed or routed; Vercel/Docker configuration still selects the old app |

## Findings requiring action

### High — UnoRouter terms and company use are unresolved

The legacy code originally included UnoRouter in its provider list and the generic free-provider fallback defaulted to it, despite README statements describing it as personal-test-only. The current UnoRouter Terms (last updated 2026-10-20) state that UnoRouter does not offer business-customer accounts and impose additional routing/data restrictions for business customers. This branch now adds a fail-closed eligibility gate that excludes UnoRouter from legacy company task routing/failover while preserving the isolated owner-triggered personal-test and read-only catalogue paths. Written provider clarification is still required before any company workload can use it.

### High — the new owner console has weaker browser credential handling

The new dashboard stores the owner API key in browser `sessionStorage`, where page scripts can read it. The legacy dashboard supports a server-managed HttpOnly session cookie. Before deployment, replace raw browser key storage with a server-managed, revocable session, exact-origin/CSRF protection, secure cookie settings, and session expiry.

### High — the worker pipeline is not end-to-end

The new API can create work items and move them through states, but it has no API for agent activation, task assignment, or queue submission in the original implementation. The worker requires an artifact sink, but no production sink implementation exists. Collaboration and learning are not persisted. The worker also needed stronger checks to ensure the assigned profile is active and its role/department match the work being executed.

The first identity-control increment has now been implemented in this branch: agent profiles persist `role_key` and `team_key`; the worker rejects missing/inactive profiles, role mismatches, department mismatches and team mismatches; owners can explicitly activate/pause/retire profiles using revision-checked, audited state changes. This does not start a worker or execute a task. A deterministic manager-led delegation preview now chooses direct manager handling, one coherent specialist team of up to five (including explicitly marked supporting roles), or owner review if capability coverage is missing. It is still only a preview and does not persist assignments or execute agents.

### High — production still points at the legacy service

- `pyproject.toml` Vercel entrypoint remains `src.ai_os.api:app`.
- `vercel.json` rewrites requests to the existing Railway AIOS API.
- `Dockerfile` starts `main.py`, the legacy entrypoint.
- No production routing has been changed. This is intentional until the independent app reaches feature and security parity.

### Medium — workforce quantity overstates role depth

The 250 specialist titles are distinct, but the current builder creates missions and capability tags mechanically from title words, with a shared template for permitted outputs and prohibitions. This is a useful routing taxonomy, not yet 250 deeply specified specialists with differentiated procedures, quality rubrics, context needs, and team collaboration contracts. The next workforce-quality pass should enrich role definitions from OpenCompany requirements, not copy external role prompts.

### Medium — persistent operational records are incomplete

The new SQLite store currently persists agent profiles, work items and audit events. It does not persist model execution attempts, artifacts, handoffs, approvals, learning experiences/proposals, or a durable usage ledger. The queue's own SQLite table is not yet connected to API-created work. Audit hashes are tamper-evident, not tamper-proof; backups, restore drills, and external audit anchoring remain necessary.

### Medium — documentation and CI can be misread

- The quarantine register previously described only nine roles and a read-only API; it is stale relative to the 261-role catalogue and owner write endpoints.
- The README contains contradictory UnoRouter claims: an earlier section describes it as a default agent provider, while a later section says personal-test-only.
- The Vercel validation workflow runs tests on pull requests, but its actual Vercel Build Output step runs only on manual dispatch against `main` and only when Vercel credentials are configured. A green PR workflow with that job skipped is not proof that the new app builds for Vercel.
- The regular test workflow verifies Python tests, not production deployment or live provider inference.

## Clean-room and provenance boundary

The new `opencompany_core` and `opencompany_app` code paths are separate from the legacy `ai_os` package. A static scan of all 23 new OpenCompany source files found no imports from `ai_os` and no remote Agency-Agent role-instruction URL. The only outbound network adapter in the new source is the explicitly configured OpenRouter model adapter. The new API does not import the Agency-Agent manifest or fetch its role Markdown. The legacy manifest, source registry, remote role loader, and associated legacy tests remain in the repository and must remain quarantined from the new runtime. Preserve provenance history; do not erase commits to conceal earlier source exposure.

A source-level similarity review and qualified legal review are still required before public or commercial distribution. An independent rewrite reduces risk but cannot guarantee that no claim will arise.

## Ordered next steps

1. Build durable manager-led assignment/delegation records and subtask creation on top of the new team-selection preview.
3. Persist handoffs, artifacts, execution attempts, model usage and learning proposals.
4. Add a production-grade artifact store and connect queue enqueue/claim/complete to the API and supervised worker process.
5. Add a compliant, verified provider adapter. Keep UnoRouter disabled for company workloads pending written provider clarification; do not send customer/confidential data to consumer free endpoints.
6. Replace dashboard API-key storage with revocable HttpOnly sessions and harden API security.
7. Re-author the specialist contracts with meaningful differentiated responsibilities and evaluation rubrics.
8. Replace legacy deployment entrypoints only after feature parity, migration/rollback plans, backup/restore, security review and end-to-end tests.
9. Remove or isolate quarantined legacy material from release/build inputs and complete the SBOM/licence/provenance review.

## Verification after the first remediation increment

- Latest tested code commit: `de35ed9e99c829586feea4b2070c36b21e2e3f7f`.
- GitHub Actions: **225 passed, 1 warning**.
- The tested changes include schema v2 role/team identity, owner-controlled audited agent state transitions, worker active/role/department/team validation, the manager delegation preview, and the UnoRouter company-routing exclusion.
- A later documentation-only commit is on the branch; its test run was still in progress at the time this audit note was updated.
- PR #105 remains draft, unmerged and mergeable. The PR currently changes 59 files; it is 146 commits ahead and 2 commits behind the latest `main`.
- The Vercel workflow's PR job runs tests only. Its Vercel Build Output job is skipped on pull requests, so there is no Vercel build/deployment verification.

## Safety and release boundary

PR #105 remains draft and unmerged. This audit and the identity-control implementation do not authorize production deployment, merge, database migration, credential rotation, paid API calls, purchases, publishing, customer contact, or financial actions. All agent profiles remain draft unless an owner explicitly changes their state; profile activation does not start workers.
