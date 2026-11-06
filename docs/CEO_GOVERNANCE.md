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

The current repository has a single-owner API token and deterministic planning/queue primitives. This governance module is a policy evaluator, not proof of autonomous AI execution or a secure multi-agent identity system. The current API's `/governance/evaluate` route is a policy-preview endpoint protected by the existing owner API gate; it does not authenticate a real agent identity. The current worker does not invoke AI models or external tools. As a fail-closed safeguard, `POST /approvals` rejects owner-token requests with HTTP 403 until a trusted CEO runtime identity exists. This deliberately means no approval request can currently be created through the API. A future execution runtime must pass authenticated agent identity to this policy at every tool boundary, make the CEO the only component allowed to create owner-approval requests, bind approvals to exact action parameters, and re-check approval immediately before execution.

## Owner control

No agent may bypass the CEO gateway. No approval may be inferred from a prior approval for a different action, a changed amount/target, or a different publication. Approval is specific, auditable, and one-time unless a narrowly scoped recurring authorization is later designed and explicitly approved.

## Signed internal agent identity foundation

The repository includes `ai_os.identity`, a server-side HMAC-SHA256 identity primitive. It issues short-lived (maximum five-minute) tokens only for enabled agents resolved through the server-side registry. Tokens bind the agent to one company run and an explicit, bounded list of capabilities. The signing key must be supplied through `AI_OS_AGENT_SIGNING_KEY` with at least 32 characters.

Verification checks the signature, audience, issue/expiry times, run binding, and optional required capability. `consume_agent_token` additionally records the token nonce in SQLite under a unique constraint; concurrent or subsequent replay attempts fail closed. The database stores the consumed nonce, agent, run, and expiry. Expired nonce rows may be pruned operationally; pruning is not required for replay safety because nonce uniqueness is retained until rows are removed.

This remains a security foundation, not an enabled autonomous execution system. There is no public token-issuance endpoint, no HTTP route currently trusts these tokens, and the worker still does not invoke AI models or external tools. Only trusted server code may call the issuer after resolving an enabled agent from the registry. Tokens must never be placed in prompts, work packets, client responses, or logs.

The current worker and company-run reporting endpoints are not yet wired to issue or consume these identities. Therefore, the token primitive does not yet authenticate agent reports or authorize tools. The approval API remains closed until a runtime boundary enforces verified principals at every tool boundary, CEO-only owner approval, exact action-parameter binding, one-time approval consumption, and execution-time revalidation. No external action is enabled by this change.
