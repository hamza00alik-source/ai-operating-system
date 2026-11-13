# Product & R&D implementation status

This document distinguishes committed implementation from runtime verification. The feature is on an isolated branch and is not production-deployed.

## Implemented in the current feature branch

- Owner-authenticated Product & R&D workflow endpoints for create, list, detail, stage delegation, stage synchronization, human preview confirmation, QA rework, and internal owner review.
- Nine ordered stages: opportunity brief, product specification, production plan, artifact generation, automated QA, human preview, packaging, listing packet, and CEO review.
- Workflow records are bound to one commercial business unit and have a database-enforced USD 0 ceiling and external-actions-disabled flag. Actual worker-reported inference costs are recorded per stage; any non-zero amount is rejected.
- Product stages create normal OpenCompany work items in the same business scope. Opportunity research routes to Intelligence & Research, specification/production/packaging to Product & Innovation, listing preparation to Revenue & Partnerships, and final executive review to the CEO role.
- Manager stages use the existing AI manager-planning and delegation-proposal flow. The owner must approve the proposal before child tasks are materialized. Specialist work is separately queued and reviewed through the existing lifecycle.
- CEO review uses the existing CEO profile and owner-reviewed work-item deliverable path.
- A stage can be synchronized only from a completed, owner-reviewed work item and its persisted deliverable.
- The OUTPOST pilot generator creates 30 original geometric SVG prototype icons, a 6×5 SVG contact sheet, a manifest, README, draft-only license notice, and ZIP archive using deterministic local code.
- ZIP generation uses fixed archive timestamps for reproducibility. QA checks ZIP CRC integrity, duplicate/path-traversal entries, required files, icon count, manifest inventory and hashes, and SVG XML parsing.
- Generated artifact names, SHA-256 hashes, sizes, and download references are recorded in workflow stage evidence.
- QA failures block the workflow. The owner can return the workflow to artifact generation; downstream stages are reset.
- Artifacts are stored under a configurable local root and served through an allowlisted, owner-authenticated download route with path and symlink checks.
- A mobile-friendly Product & R&D panel is injected into the existing owner dashboard. It exposes workflow creation, delegation, team-proposal approval, specialist/manager execution, owner review, artifact generation, preview review, rework, and internal workflow approval.

## Explicitly not implemented or not verified

- This pilot generator produces SVG only. It does not create PNG exports, multi-resolution raster assets, or target-engine import configurations.
- The geometry is a procedural prototype, not a professionally art-directed finished game UI asset pack.
- No independent visual-quality review has been completed. The owner preview checkpoint is still required.
- No game-engine compatibility, accessibility, licensing/IP, or market-demand validation has been performed.
- Product discovery research is only as strong as the evidence supplied to or retrieved by the research roles; the workflow does not manufacture market proof.
- The system does not publish marketplace listings, contact buyers, purchase services, initiate payments, or make customer commitments.
- Manager planning and specialist delegation use the existing free-provider-gated planner. A complete multi-agent round trip has not yet been executed in a live runtime.
- Agent execution depends on correctly provisioned and explicitly ACTIVE profiles, an owner-tested zero-cost provider, and explicit owner queue admission. If those prerequisites are absent, the workflow stops with a blocker.
- The current Product & R&D workflow does not claim 511 agents are continuously running. It uses the existing role contracts and the existing durable worker system.

## Verification boundary

Tests have been added for workflow state, audit, business isolation, QA failure/rework, deterministic archive generation, and path validation. They have deliberately not been run under the owner's testing pause through 2026-12-01. No claim of runtime or integration-test success is made.

Before merge or production use, run the approved test suite after the testing pause, inspect the actual generated preview, validate the worker/manager/specialist round trip, inspect artifact storage on the intended persistent volume, and complete a security review of the new endpoints and storage paths.


## Follow-up static review — 2026-11-13

- Tightened delegation proposal validation so both AI-generated and deterministic manager proposals require the department manager profile to be explicitly ACTIVE.
- Tightened both specialist-selection paths so every proposed specialist profile must be explicitly ACTIVE before a proposal can be created. The approval endpoint continues to re-check profile state and identity before materializing tasks, protecting against state changes between planning and approval.
- Corrected Product & R&D stage delegation to validate each role against its canonical team: department managers use the management team, the CEO uses executive, and specialist roles use their workforce-catalogue team. This avoids incorrectly requiring every non-CEO role to belong to management.
- Corrected stage synchronization for specialist-owned work: the completed stage parent may be authored by the canonical department manager after owner-approved specialist prerequisites, and sync now revalidates those same-business completed prerequisites and persisted deliverables. Direct assignment to the stage owner remains valid.
- This is a static code correction only. The test pause remains in force; no tests or runtime execution were performed.


## Opt-in background coordinator — 2026-11-13

- Added `ProductRDCoordinator`, invoked by one worker-fleet thread at a bounded interval when `OPENCOMPANY_PRODUCT_RD_AUTOMATION=true`. The default is disabled.
- The coordinator can create the next stage's internal DRAFT work item when its canonical role profile is explicitly ACTIVE and correctly assigned. It never approves the manager's delegation proposal, changes the work item to READY, admits it to the queue, or starts inference.
- It can synchronize a stage only after its attached work item is COMPLETED through the existing owner-review lifecycle, with a persisted deliverable and validated business, role, team, manager-synthesis dependencies, and zero actual cost.
- It can generate the OUTPOST local SVG prototype and run deterministic QA automatically when that exact pilot reaches artifact generation. This uses local deterministic code only; failed QA blocks the workflow as before. Human preview remains a hard owner checkpoint.
- Automated stage/work-item audit events identify the system coordinator rather than impersonating the owner.
- Worker status exposes whether maintenance is configured and the number of successful/failed maintenance cycles.
- This is opt-in and inactive by default. It only runs while the owner-started worker fleet is running (which still requires a successful owner-triggered zero-cost provider test). No paid calls, automatic delegation approval, queue admission, owner deliverable approval, external actions, or publishing were added.
- Added unexecuted coordinator tests for local OUTPOST generation/QA progression and the absence of draft creation when no ACTIVE role profile exists.
- Static implementation only: no tests or runtime execution were performed under the testing pause.


## Opt-in AI manager-proposal preparation — 2026-11-13

- Added a separate `OPENCOMPANY_PRODUCT_RD_AUTO_PROPOSALS` switch, defaulting to false and subordinate to `OPENCOMPANY_PRODUCT_RD_AUTOMATION=true`.
- When enabled, the background coordinator may ask the existing department-manager planner to prepare one proposal for an unassigned DRAFT stage work item. The existing model gateway is called with a USD 0 request budget and the confirmed-free provider route; provider/cost failures remain fail-closed.
- Manager and specialist profiles are revalidated as explicitly ACTIVE and correctly assigned before proposal persistence. Existing proposals for the same parent prevent repeat planning on later ticks.
- The proposal and child tasks remain DRAFT. This feature does not approve proposals, materialize READY work, enqueue work, start inference for the child tasks, approve deliverables, or perform external actions. Owner approval remains required before the existing delegation-approval endpoint can materialize READY tasks.
- `/workers/queue` reports whether this additional automation is enabled.
- Added a static unit test for default-off behavior and proposal idempotency. Tests remain unexecuted during the owner's testing pause through 2026-12-01.
