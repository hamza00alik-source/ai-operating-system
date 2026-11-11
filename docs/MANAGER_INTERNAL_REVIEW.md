# Manager-led specialist review

OpenCompany supports an internal manager quality gate for specialist drafts.

## Endpoint

`POST /work-items/{item_id}/manager-review`

The HTTP endpoint is owner-authenticated. In addition, the API runtime wires the same audited review workflow into the worker completion lifecycle. Set `OPENCOMPANY_AUTO_MANAGER_REVIEW=true` to enable that internal trigger; it defaults to false. The model is instructed to act as the assigned department manager. The manager profile must be ACTIVE, belong to the same department, and use the department's canonical manager role. A manager cannot review its own work item.

## Decision behavior

- The manager model receives the registered manager role's mission, workflow, quality rubric, work objective, and specialist deliverables as untrusted evidence.
- Evidence is capped at eight deliverables, 6,000 characters per deliverable, and 24,000 combined characters. Oversized evidence is rejected rather than silently truncated.
- The response must be strict JSON with an explicit boolean decision, rationale, and (when rejected) actionable rework instructions.
- Invalid, incomplete, or ambiguous model output fails closed; it does not approve the work.
- Accepted specialist work moves to COMPLETED through the existing audited review transition. If all approved delegation prerequisites are complete and automatic queue admission is enabled, the manager synthesis task can be queued.
- Rejected work returns to READY. The rework instructions are attached to the task objective and the specialist task is automatically requeued only when automatic queue admission is enabled and a zero-cost provider is available.
- All model inference uses the zero-dollar request budget and the configured UnoRouter gateway. No paid fallback is introduced.
- A worker invokes the manager gate only after the specialist deliverable and REVIEW transition are durably saved. The worker lease is then acknowledged after the manager attempt.
- If the manager callback fails (for example, no active manager, no eligible free model, or invalid model output), the deliverable remains in REVIEW, a `manager.review_deferred` audit event records only the error type, and the worker does not discard or rerun the specialist deliverable. The owner can retry through the authenticated endpoint.
- On worker recovery, an already-persisted REVIEW deliverable re-enters the manager gate; an already-completed item is acknowledged without repeating the review.

## Boundaries

This is an internal quality-control stage, not permission to publish, contact customers, purchase, spend, deploy, or make commitments. The final manager synthesis deliverable remains subject to owner review. The internal trigger is event-driven by worker completion when the feature flag is enabled; it is not a periodic retry scheduler. Deferred reviews remain visible in REVIEW and can be retried by the owner through the authenticated endpoint.
