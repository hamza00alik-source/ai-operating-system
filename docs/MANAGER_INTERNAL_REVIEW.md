# Manager-led specialist review

OpenCompany supports an internal manager quality gate for specialist drafts.

## Endpoint

`POST /work-items/{item_id}/manager-review`

The endpoint is owner-authenticated. The owner dashboard/operator invokes it; the model is instructed to act as the assigned department manager. The manager profile must be ACTIVE, belong to the same department, and use the department's canonical manager role. A manager cannot review its own work item.

## Decision behavior

- The manager model receives the registered manager role's mission, workflow, quality rubric, work objective, and specialist deliverables as untrusted evidence.
- Evidence is capped at eight deliverables, 6,000 characters per deliverable, and 24,000 combined characters. Oversized evidence is rejected rather than silently truncated.
- The response must be strict JSON with an explicit boolean decision, rationale, and (when rejected) actionable rework instructions.
- Invalid, incomplete, or ambiguous model output fails closed; it does not approve the work.
- Accepted specialist work moves to COMPLETED through the existing audited review transition. If all approved delegation prerequisites are complete and automatic queue admission is enabled, the manager synthesis task can be queued.
- Rejected work returns to READY. The rework instructions are attached to the task objective and the specialist task is automatically requeued only when automatic queue admission is enabled and a zero-cost provider is available.
- All model inference uses the zero-dollar request budget and the configured UnoRouter gateway. No paid fallback is introduced.

## Boundaries

This is an internal quality-control stage, not permission to publish, contact customers, purchase, spend, deploy, or make commitments. The final manager synthesis deliverable remains subject to owner review. The owner-authenticated endpoint remains available for manual review. An optional worker-lifecycle trigger is also implemented: set `OPENCOMPANY_AUTO_MANAGER_REVIEW=true` to invoke the same strict, zero-budget manager review immediately after a specialist deliverable is durably saved and its queue lease is acknowledged. Accepted work becomes completed; rejected work returns to READY with the manager's instructions attached and is re-admitted to the same active specialist queue with an audit event. The feature is disabled by default. If the provider or review is unavailable, the task remains in REVIEW and the specialist is not re-executed. Manager synthesis/CEO escalation and product-workflow executor integration are still separate follow-on work.
