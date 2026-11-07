# CEO governance and single approval gateway

## Non-negotiable company rule

The CEO agent (registry ID: `company-orchestrator`) is accountable for every action performed by the company. Department agents are delegated specialists; they do not independently make owner-level decisions or contact the owner for approval.

## Decision flow

1. A department agent proposes or performs permitted internal work within its assigned role.
2. The CEO coordinates, assigns, reviews, and remains accountable for delegated work.
3. A sensitive or external action is escalated to the CEO.
4. The CEO prepares one complete approval request for the owner, including the action, target, cost (if any), expected effect, risks, and rollback/refund details where relevant.
5. The system waits for the owner's explicit approval or rejection. Silence is not approval.
6. Only after approval may an execution adapter perform the approved action, and only within the exact approved scope.

## Internal work allowlist

The initial allowlist covers research, analysis, drafting, planning, task assignment, work-packet creation, testing, summarization, internal knowledge updates, listing/content draft preparation, support classification, draft replies, and metrics review.

## Owner approval required

The initial approval list includes publishing content/products/listings; sending external messages or campaigns; customer commitments; refunds; spending, purchases, paid promotion or subscriptions; production changes and public deployment; security/permission changes; and financial-setting changes.

## Fail-closed behavior

An unregistered/disabled agent is blocked. An action not explicitly classified as internal or owner-approval-required is blocked for policy review. Department agents attempting an owner-approval action receive `escalate_to_ceo`; only the CEO can submit it for owner approval.

## Important implementation boundary

The repository has a single-owner API token gate, signed internal agent identities, and deterministic planning/queue primitives. The `/governance/evaluate` route remains a policy-preview endpoint; it does not itself authorize a tool call. The legacy `POST /approvals` route remains closed to owner-token callers. The new `POST /ceo/approval-requests` route accepts only a signed CEO identity with the `approval.request` capability, while owner inbox and decision routes require the owner API token. This is a narrow approval workflow, not proof of autonomous AI execution or a secure general-purpose tool system.

## Owner control

No agent may bypass the CEO gateway. No approval may be inferred from a prior approval for a different action, a changed amount/target, or a different publication. Approval is specific, auditable, and one-time unless a narrowly scoped recurring authorization is later designed and explicitly approved.

## Signed internal agent identity foundation

The repository includes `ai_os.identity`, a server-side HMAC-SHA256 identity primitive. It issues short-lived (maximum five-minute) tokens only for enabled agents resolved through the server-side registry. Tokens bind the agent to one company run and an explicit, bounded list of capabilities. The signing key must be supplied through `AI_OS_AGENT_SIGNING_KEY` with at least 32 characters.

Verification checks the signature, audience, issue/expiry times, run binding, and optional required capability. `consume_agent_token` additionally records the token nonce in SQLite under a unique constraint; concurrent or subsequent replay attempts fail closed. The database stores the consumed nonce, agent, run, and expiry. Expired nonce rows may be pruned operationally; pruning is not required for replay safety because nonce uniqueness is retained until rows are removed.

This remains a security foundation, not an enabled autonomous external-action system. There is no public token-issuance endpoint. The specialist report route and the exact CEO approval ingress verify signed tokens; only trusted server code may mint them after resolving an enabled agent from the registry. Tokens must never be placed in prompts, work packets, client responses, or logs.

The company-run step-report endpoint now requires an `X-AI-Agent-Token` header. It resolves the assigned agent from the persisted run step, then verifies the token against that exact agent ID, run ID, and the `step.report` capability before atomically consuming its nonce. Missing tokens are rejected, wrong-agent/wrong-run tokens are rejected, and a consumed token cannot be replayed. The endpoint records a separate audit event under the verified agent identity after a report is accepted.

This is a narrow authenticated reporting boundary only. The model-backed specialist worker executes bounded analysis tasks, but there is still no general tool authorization gateway or external-action adapter. No external action is enabled.


## Exact-scope owner approval foundation

The internal identity issuer now applies a server-side capability policy: the CEO may receive only `approval.request`; enabled specialist agents may receive only `step.report`. Verification repeats the policy check and confirms the agent remains enabled. A caller cannot request arbitrary capabilities by supplying a string to the issuer.

The new `ai_os.approvals` module provides internal primitives (not HTTP endpoints) for:
- canonicalizing an allowlisted action and its complete JSON parameters, then hashing that exact scope with SHA-256;
- creating a pending request only from a signed, run-bound CEO identity with `approval.request`, consuming that credential's nonce exactly once;
- recording an owner decision against the exact action hash, with expiry and a single pending-to-decided transition;
- atomically consuming an approved request only when action type and every parameter still match, with a unique execution ID and one-time state transition.

A CEO request token is consumed only after the action has passed canonical validation, and cannot create a second approval request. Approval requests receive a maximum 15-minute owner-review window after the signed CEO request has been verified; the CEO token itself remains short-lived and is not needed for the owner to finish reviewing an already-created request. Expired requests transition to `expired`; rejected, changed, expired, or already-consumed approvals cannot authorize execution. Parameter JSON is bounded to 16 KB and rejects non-finite values.

**The HTTP approval workflow is now enabled, but external execution is not.** `POST /ceo/approval-requests` verifies and consumes a signed CEO token, requires an existing company run, and accepts only the owner-approval action allowlist. `GET /owner/approval-requests` and `POST /owner/approval-requests/{id}/decision` remain behind owner authentication. The owner decision must include the exact SHA-256 action hash shown in the inbox. Requests expire after at most 15 minutes, and creation/decisions are audit-logged. The old `/approvals` route remains closed to caller-claimed CEO identity. `consume_owner_approval` is still an internal server-side primitive only; there is no adapter or route that consumes an approval to publish, message customers, spend, deploy, or change production. External actions remain disabled.


## HTTP CEO-to-owner approval workflow

- CEO ingress: `POST /ceo/approval-requests` with `X-AI-Agent-Token`; only the signed `company-orchestrator` identity with `approval.request` is accepted. The token is one-use and bound to an existing company run.
- Owner inbox: `GET /owner/approval-requests` is protected by the owner bearer token and returns the exact action parameters, expiry, and SHA-256 scope hash.
- Owner decision: `POST /owner/approval-requests/{id}/decision` requires the owner token and exact displayed hash, and supports one irreversible approve/reject decision.
- Expired requests are marked expired. Action parameters are bounded and reject credential-like field names; integration connection IDs should be used instead of access credentials.
- Approval is not execution. A future adapter must re-check the exact approved action immediately before acting, consume it once, and record the execution result. No such external adapter is enabled today.


## Server-side action gateway

The internal `ai_os.action_gateway` module adds a trusted adapter registry and execution-time approval consumption. It refuses execution unless `AI_OS_EXTERNAL_ACTIONS_ENABLED=true`, checks for a registered server-owned adapter before consuming approval, verifies the exact approved parameters, consumes the approval once, and audits adapter start/completion/failure. It is not exposed as an HTTP route. No production adapters are registered, the flag defaults to false, and no external action is currently executable. An adapter failure leaves the approval consumed and requires manual reconciliation; automatic retries are intentionally prohibited. See [ACTION_GATEWAY.md](ACTION_GATEWAY.md).


## CEO review to owner-approval handoff

After a model-assisted CEO review, the trusted server-side CEO review module may turn justified proposals into signed, run-bound owner-approval requests. The CEO identity token is minted inside the server runtime, is limited to `approval.request`, is short-lived and one-use, and is never returned to the browser or included in the review record.

The proposal path currently supports only two narrow actions: `create_website_draft` (exactly `title` and `content`) and `create_product_draft` (exactly `name`, `description`, and `regular_price`). These actions create unpublished drafts only. The server rejects unsupported actions and credential-like parameter keys. The owner still sees the exact parameters and hash, must explicitly approve or reject, and must separately trigger execution. This path does not publish content or products, send messages, spend money, or deploy services.

CEO-generated approval requests are recommendations for owner review, not proof that a product is commercially or legally ready. Verify content, intellectual-property rights, pricing, tax treatment, and destination store before approving any draft creation.
