# Manager delegation proposals

The independent OpenCompany core now supports durable, owner-authenticated
manager delegation proposals.

## Flow

1. The owner creates a parent work item.
2. The owner requests a deterministic delegation preview by required capability.
3. The owner may persist that plan with
   `POST /work-items/{id}/delegation-proposals`.
4. The manager profile and every selected specialist profile must already be
   provisioned. A missing profile causes a conflict response; no partial plan
   is saved.
5. A proposal record and its child-task drafts are stored in SQLite. Repeating
   the same request for the same parent returns the existing proposal rather
   than creating duplicates.
6. The owner can inspect saved proposals through
   `GET /work-items/{id}/delegation-proposals`.

## Safety boundary

- Proposals and child tasks remain in `draft` state.
- No agent is activated or paused by proposal creation.
- No parent work-item state is changed.
- No queue entry is created and no worker is started.
- No model request, external integration, publication, customer message,
  purchase, payment, or other external side effect occurs.
- The persisted child-task record identifies its parent, assigned draft
  profile, role and team. It is a proposal record, not yet a runnable
  `WorkItem` or worker-queue payload.
- Repeated identical requests are idempotent; a changed capability request
  creates a separate proposal.

## Remaining work

The next integration step is an explicit owner approval transition that
materializes approved child records into normal work items and durable queue
entries. That step must validate current agent state/revisions, dependencies,
quotas and policy gates transactionally. The production dashboard session
model and artifact sink remain separate release blockers.
