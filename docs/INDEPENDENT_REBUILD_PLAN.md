# OpenCompany Independent Rebuild Plan

**Branch:** `clean-room-rebuild`  
**Baseline:** `main` at the time this branch was created  
**Method:** Requirements-first, independently authored implementation  
**Release rule:** No merge or production deployment without a separate owner decision.

## Goal

Replace any functionality that depends on reference-repository code or expressive materials with an independently designed OpenCompany implementation. Improve reliability and capability through measurable requirements, tests, and operational evidence.

## Non-negotiable constraints

- Do not copy or reuse code, prompts, agent role definitions, tests, templates, docs, distinctive structures, or assets from Agency-Agent or reference repositories.
- Do not fetch or load Agency-Agent role prompt files at runtime.
- Do not treat paraphrasing, renaming, code translation, or superficial restructuring as a clean-room rewrite.
- Preserve existing Git history and work; isolate uncertain material rather than concealing its origin.
- Zero-starting-budget: no paid API calls, services, subscriptions, or metered actions without explicit approval.
- No production changes, migrations, publishing, customer contact, spending, purchases, or financial commitments.
- Keep human approval gates for consequential external actions.

## Initial repository findings

The private repository `hamza00alik-source/ai-operating-system` is a Python/FastAPI project with SQLite persistence, a provider gateway, owner dashboard, workflows, agent runtime, memory, authentication, tests, and deployment configuration.

The current README explicitly describes:
- A 283-role specialist catalogue sourced from `hamza00alik-source/agency-agents`.
- A manifest at `data/agency_agents_manifest.json`.
- Runtime retrieval of specialist instruction files from the Agency-Agent repository.

Those materials and runtime dependencies are incompatible with the new no-reuse rule. They are quarantined from the replacement design and must be replaced by original OpenCompany role specifications authored from business requirements.

The source inventory lists Agency-Agent, Automaton, and other company/platform references. It is to be treated as provenance evidence only, not as an implementation recipe.

## Workstreams

### A. Provenance and quarantine
- Inventory every tracked file and its origin.
- Classify each item as independently authored, third-party-derived, mixed, or unknown.
- Identify imported agent definitions, prompts, code, tests, templates, copied docs, and assets.
- Prevent quarantined data and runtime URLs from being loaded by the replacement.
- Preserve audit evidence and Git history.

### B. Product requirements
Write original OpenCompany requirements for:
- Company command and task planning.
- Specialist role definitions and departmental responsibilities.
- Agent lifecycle and execution contracts.
- Collaboration, delegation, handoffs, and dependency management.
- Persistent memory, knowledge provenance, and retrieval permissions.
- Learning through evaluations and owner-approved improvement proposals.
- Provider-neutral model access and strict cost controls.
- Tool and integration permissions.
- Approval workflows, audit events, retries, and recovery.
- Owner dashboard and operational reporting.

### C. Independent architecture
Design original interfaces and data models for:
- Task and workflow orchestration.
- Agent registry and lifecycle.
- Durable queue, worker leases, retries, and scheduling.
- Multi-agent collaboration and artifact exchange.
- Memory, knowledge sources, and evaluation records.
- Tool gateway and permission policy.
- Model gateway with provider failover that cannot silently select paid services.
- Human approvals and tamper-evident audit trail.

### D. Implementation sequence
1. Provenance inventory and quarantine plan.
2. Requirements and acceptance criteria.
3. New core domain model and persistence contracts.
4. New scheduler, queue, and worker lifecycle.
5. New agent registry and original OpenCompany role library.
6. New collaboration, workflow, and artifact system.
7. New memory and evaluation-based improvement loop.
8. New tool permissions and integrations.
9. Owner console, observability, and reporting.
10. Security, licence, regression, and deployment-readiness review.

Each stage must be independently testable and must not break the existing production service.

### E. Verification
For every stage, record:
- Requirement and acceptance criteria.
- Design and implementation provenance.
- Tests and results.
- Dependency/licence review.
- Security and cost review.
- Known limitations and rollback approach.

## First implementation target

The first code milestone should be an independently designed OpenCompany core contract: domain entities and interfaces for tasks, agents, execution attempts, artifacts, approvals, and audit events. It must be derived from the requirements above, not copied from any reference implementation.

## Completion definition

The rebuild is ready for a separate release review only when:
- Reference-repository source code and content are not used by runtime or build processes.
- All required components have documented independent provenance.
- Required tests and security checks pass.
- The software bill of materials and licence notices are complete.
- Existing user data and production behaviour have a tested migration/compatibility plan.
- The owner has reviewed and separately approved any merge or deployment.


## Independently designed organization and owner control plane

The clean-room implementation now defines ten OpenCompany departments in a new department contract. This design was derived from OpenCompany's business objectives and does not import the quarantined legacy department file.

Each department declares a mission, accountabilities, manager role, member role assignments, decision scope, success measures, and approval boundaries. The workforce currently contains ten original role specifications. An owner-authenticated, idempotent bootstrap operation can create ten persistent manager profiles in draft state; this does not activate agents.

A responsive owner console is served at /owner. It displays departments, manager profiles, work items, provider readiness, and media capability state. Its bootstrap control creates draft profiles only.

## Zero-budget model and media capability

A fixed-model OpenRouter adapter is implemented for explicit model IDs ending in :free. It uses persistent quota reservations capped at 50 requests per UTC day and 20 per rolling minute, and has no paid fallback. Activation requires a key, a model ID, and explicit free-tier confirmation. No live credentials are stored in the repository and no real inference has yet been verified.

Groq and Cloudflare Workers AI remain candidate providers pending account-specific zero-cost verification. No paid usage or automatic fallback is permitted.

LongCat-Video is registered under Media & Creative Production as researched_not_connected. It is not installed or active. Compute availability, model weights, dependencies, licence and a zero-cost execution path must be verified before activation.

## New acceptance criteria

- Department and role catalogues contain only independently authored OpenCompany definitions.
- Department-manager bootstrap is owner-authenticated, idempotent, auditable, and creates draft profiles only.
- The owner console does not store the owner key beyond tab session storage and does not expose private data without authentication.
- Free model configuration is fixed to a verified free model ID and fails closed on missing confirmation, quota exhaustion, provider errors, or model substitution.
- Video generation remains disabled until compute, licensing, storage and zero-cost execution are verified.
