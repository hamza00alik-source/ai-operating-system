# Clean-room integration and operational-readiness audit — 2026-11-25

## Scope

Read-only source audit of the newer `opencompany_v2/` clean-room package against the primary `opencompany_app` runtime on branch `opencompany-merged-clean`. This audit does not connect services, start workers, publish products, contact customers, move money, or change production behavior.

## Findings

### I-01 — The clean-room package is not integrated into the primary application

**Evidence**
- `opencompany_v2/src/opencompany/runtime.py` composes the clean-room `Brain`, `SkillRegistry`, and `Worker` classes.
- `src/opencompany_app/runtime.py` and `src/opencompany_app/api.py` are the primary application's runtime and API modules; the inspected primary API imports `opencompany_core` and `opencompany_app`, not the `opencompany_v2` package.
- The PR description itself states that `opencompany_v2` remains a separate subproject and has not yet been wired into `opencompany_app`.

**Impact**
Passing tests for `opencompany_v2` do not prove that its memory, skills, queue, or worker capabilities are available through the deployed owner dashboard or primary API. The repository currently contains two implementation lines rather than one integrated operating runtime.

**Required correction**
Choose and document the canonical runtime boundary, then integrate selected clean-room modules behind the existing owner-authenticated API with migration, compatibility, and regression tests. Do not represent clean-room package features as live primary-app capabilities before this is verified.

### I-02 — Clean-room execution is a bounded primitive, not a complete autonomous company

**Evidence**
- `opencompany_v2/src/opencompany/ceo.py` ranks supplied opportunity records and validates bounded plans; it does not itself execute research, assign real-world work, or operate external services.
- `opencompany_v2/src/opencompany/skills.py` provides an in-process registry and invokes explicitly registered Python handlers.
- `opencompany_v2/src/opencompany/runtime.py` requires explicit handler routes and a server-side approval resolver for sensitive actions.
- `opencompany_v2/src/opencompany/worker.py` executes registered handlers from a queue; it is not a general-purpose model/tool agent loop.

**Impact**
The package supplies useful orchestration primitives, but not yet a verified always-on multi-agent workforce with connected research, marketplace, social, or commerce tools.

**Required correction**
Integrate one vertical slice at a time: authenticated task creation, persisted assignment, approved handler execution, auditable result, and owner review. Measure actual worker heartbeats and completed tasks rather than counting agent profiles or templates.

### I-03 — Customer-contact approval is not an explicit action in the clean-room policy

**Evidence**
- `opencompany_v2/src/opencompany/permissions.py` defines `Action` values for read, research, draft creation, internal modification, publishing, spending, customer commitments, refunds, and production changes.
- The enum does not define a distinct `contact_customer` / external-message action.
- `Skill.validate()` in `opencompany_v2/src/opencompany/skills.py` rejects action strings that are not members of `Action`, so an unrecognized contact action fails closed rather than being executable.

**Impact**
The current implementation does not provide a first-class, testable permission category for sending an ordinary external message that is not itself a customer commitment. The rejection is fail-closed, but the policy is incomplete and difficult to audit against the owner's no-send-before-approval rule.

**Required correction**
Before any external communication adapter is added, introduce explicit action types for external communication/customer contact and require an auditable, server-side owner approval record for every send. Test that job payloads cannot self-approve and that missing, expired, or mismatched approval blocks the action.

### I-04 — Marketplace channel readiness is a data model, not a connected integration

**Evidence**
- `opencompany_v2/src/opencompany/channels.py` defines channel metadata and boolean readiness fields for seller eligibility, account connection, credentials, connection test, and publishing permission.
- The inspected module contains no marketplace API client, OAuth flow, seller-account verification, listing upload, or payout connection.
- `ready_for_publish()` only evaluates those stored booleans.

**Impact**
A channel marked ready based only on these fields would not, by itself, prove that the marketplace account or publishing API works. The module is a readiness checklist, not a functioning Etsy, Gumroad, itch.io, or storefront connector.

**Required correction**
Keep channel states unverified until a real provider adapter completes an authenticated, non-publishing connection test and records provenance. Publishing must remain blocked behind explicit owner approval even after connectivity is verified.

### I-05 — Clean-room README contains a skill-assignment status discrepancy

**Evidence**
- `opencompany_v2/README.md` says skill assignments are not backed by persistent storage.
- `opencompany_v2/src/opencompany/store.py` implements persisted skill assignment operations (including assignment listing and unassignment).
- `opencompany_v2/tests/test_controls.py` exercises persisted assignment, version conflict, missing-capability rejection, and prohibited-action rejection.

**Impact**
The README understates the implemented persistence capability, while the PR still correctly notes that the clean-room package is not exposed through the primary owner dashboard.

**Required correction**
Update the README to distinguish what is persisted inside the clean-room package from what is integrated/exposed in the primary application. Do not change runtime behavior merely to resolve this documentation discrepancy.

## Verified boundaries

- The clean-room permission policy defaults sensitive actions to approval-required and the worker handler obtains approval from a server-side resolver rather than trusting a job payload.
- The clean-room product/channel workflow distinguishes a product ready for owner review from a published product.
- The clean-room queue documentation correctly describes at-least-once delivery; handlers must be idempotent because a crash can occur after a side effect but before acknowledgement.
- These are code-level safeguards and workflow primitives, not proof of production deployment or live external integrations.

## Priority order

1. Keep all external contact, publishing, spending, refunds, and production changes blocked until explicit approval is represented and enforced end-to-end.
2. Integrate one clean-room vertical slice into the primary runtime, with tests through the owner API and dashboard.
3. Add real provider adapters only after seller-region eligibility, payout availability, credential security, and zero-cost constraints are verified.
4. Correct the README status wording so documentation matches the code.

## Approval boundary

This audit is documentation-only. It does not alter financial semantics, permission behavior, worker execution, deployment configuration, or external integrations. The previously identified finance-model correction remains separately blocked pending explicit owner approval.
