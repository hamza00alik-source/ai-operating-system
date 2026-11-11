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

This prevents an untested claim (for example, visual quality, legal review, market demand, or engine compatibility) from being presented as a passed automated check.

## Safety and current scope

- The cost ceiling is fixed at USD 0 for each workflow.
- External actions are disabled in the persisted record.
- Owner approval only marks the result `approved_internal`; it does not publish, list, sell, contact customers, or authorize spending.
- The current implementation provides persisted workflow orchestration and evidence capture. It does **not** yet mean autonomous agents have generated the artifacts, run visual or legal reviews, or completed a commercial product.
- Artifact references are recorded metadata; a managed artifact store, deterministic local generator, package builder, and dashboard UI are follow-on implementation work.
