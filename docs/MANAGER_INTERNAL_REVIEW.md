# Manager-led specialist review

OpenCompany supports an internal manager quality gate for specialist drafts.

## Endpoint

`POST /work-items/{item_id}/manager-review`

The endpoint is owner-authenticated. The owner dashboard/operator invokes it; the model is instructed to act as the assigned department manager. The manager profile must be ACTIVE, belong to the same department, and use the department's canonical manager role. A manager cannot review its own work item.

## Decision behavior

- The manager model receives the work objective and bounded specialist deliverables as untrusted evidence.
- The response must be strict JSON with an explicit boolean decision, rationale, and (when rejected) actionable rework instructions.
- Invalid, incomplete, or ambiguous model output fails closed; it does not approve the work.
- Accepted specialist work moves to COMPLETED through the existing audited review transition. If all approved delegation prerequisites are complete and automatic queue admission is enabled, the manager synthesis task can be queued.
- Rejected work returns to READY. The rework instructions are attached to the task objective and the specialist task is automatically requeued only when automatic queue admission is enabled and a zero-cost provider is available.
- All model inference uses the zero-dollar request budget and the configured UnoRouter gateway. No paid fallback is introduced.

## Boundaries

This is an internal quality-control stage, not permission to publish, contact customers, purchase, spend, deploy, or make commitments. The final manager synthesis deliverable remains subject to owner review. The endpoint is not a background scheduler: it must be invoked by the owner-authenticated dashboard/API until an independently validated orchestration trigger is implemented.
