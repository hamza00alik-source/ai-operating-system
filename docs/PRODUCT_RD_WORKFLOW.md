# Product & R&D workflow

The independently authored Product & R&D workflow is available through the owner-authenticated API under `/product-workflows`.

## Workflow stages

1. Opportunity brief
2. Product specification
3. Production plan
4. Artifact generation
5. Automated QA
6. Human-readable preview
7. Packaging
8. Internal listing packet
9. CEO review

Each stage stores its assigned OpenCompany role, status, timestamps, input/output, artifact references, zero-dollar cost estimate, evidence, and blockers. Stages are sequential. A blocked stage cannot be silently skipped.

## API

- `POST /product-workflows` — create an internal workflow from a title and brief.
- `GET /product-workflows` — list workflows.
- `GET /product-workflows/{id}` — inspect a workflow and its stage evidence.
- `POST /product-workflows/{id}/generate-blueprint` — when artifact generation is the active stage, create a deterministic zero-cost starter ZIP.
- `POST /product-workflows/{id}/run-automated-qa` — when automated QA is active, validate ZIP integrity, required files, safe paths, manifest checksums and scope disclosures.
- `GET /product-workflows/artifacts/{artifact_id}` — download an owner-authenticated generated ZIP.
- `POST /product-workflows/{id}/stages/{stage}/start` — start the next eligible stage.
- `POST /product-workflows/{id}/stages/{stage}/complete` — record output, artifact references, and evidence.
- `POST /product-workflows/{id}/stages/{stage}/block` — record a blocker.
- `POST /product-workflows/{id}/return-to-production` — return a blocked automated-QA job to artifact production and reset downstream stages.
- `POST /product-workflows/{id}/owner-review` — approve or reject the internal result.

All routes require owner authentication. Browser sessions also retain the existing CSRF and same-origin protections.

## QA contract

Completing `automated_qa` requires three separate arrays:
- `passed_checks`
- `failed_checks`
- `untested_claims`

Failed automated checks block the workflow and preserve failure evidence; the owner can return the job to production for rework. The current automated runner validates the generated blueprint archive only. It explicitly leaves visual quality, engine behavior, IP/licensing and market demand untested, so these claims cannot be represented as passed checks.

## Safety and current scope

- The cost ceiling is fixed at USD 0 for each workflow.
- External actions are disabled in the persisted record.
- Owner approval only marks the result `approved_internal`; it does not publish, list, sell, contact customers, or authorize spending.
- The current implementation provides persisted workflow orchestration and evidence capture. It does **not** yet mean autonomous agents have generated the artifacts, run visual or legal reviews, or completed a commercial product.
- The current deterministic generator creates a ZIP containing a product specification, production plan, unexecuted QA checklist, unpublished listing draft, source brief, and manifest. It is a starter blueprint, not a finished commercial product or final game asset.
- ZIPs are stored under the directory beside the configured SQLite database in `product_artifacts/`. On Railway this is on the persistent `/data` volume when the database uses the configured `/data` path.
- The dashboard UI, real product-specific source-asset generators, engine/visual test runners, and autonomous agent execution remain follow-on work.
