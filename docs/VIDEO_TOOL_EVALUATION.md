# Evaluation of the Three AI Tool Reels

**Status:** Evaluated; selective adoption approved  
**Scope:** Architecture and integration decisions for OpenCompany AIOS  
**Safety/cost:** No paid services, API keys, external publishing, or production deployment enabled by this evaluation.

## 1. Reel: free LLM API directory

The caption points to a directory of free-tier LLM API providers, rather than a bundle of API keys or a universal free inference service.

Candidate directory identified from the description:
- https://github.com/mnfst/awesome-free-llm-apis
- License reported by repository metadata: MIT.
- The directory describes provider base URLs, model IDs, signup links, and changing free-tier limits. Most providers require the user to create their own account and API key. The exact repository URL in the earlier draft was corrected after checking GitHub; multiple forks exist, so the catalogue is a discovery aid rather than an authoritative source.

### Decision: adopt as a discovery catalogue, not as an API source

OpenCompany must not assume that a provider is keyless, permanently free, available in Pakistan, commercially usable, or compatible with every feature just because it appears in a directory.

Implementation rules:
- Keep a small, reviewed provider catalogue in AIOS; do not import hundreds of entries blindly.
- Each entry must declare base URL, API protocol, supported capabilities, credential requirement, known quota source, commercial-use caveat, last-verified date, and enabled/disabled status.
- Store credentials only in environment/secret storage, never in Git, logs, prompts, or provider catalogue files.
- Default all new providers to disabled until verified.
- Distinguish keyless, free-tier-with-own-key, trial-credit, and paid access.
- Do not automatically rotate through accounts, evade rate limits, scrape keys, or use unofficial reverse-engineered endpoints.
- Never auto-fallback to a paid model. Enforce per-task request/token ceilings and report quota/rate-limit errors clearly.
- The provider directory is a lead list; current terms and quotas must be rechecked at the provider's own official documentation before activation.

The first functional test should use a provider the owner explicitly configures, or a legitimate public keyless endpoint only if its operator documents that access. A public GitHub repository does not itself grant access to provider APIs.

## 2. Reel: Orca multi-agent coding orchestrator

Source: https://github.com/stablyai/orca

The current repository README describes a desktop-oriented AI coding orchestrator with agent coordination, parallel Git worktrees, reviewable diffs, Git integration, remote execution, and a mobile companion. It is MIT-licensed. Its documented examples include coding-agent products the OpenCompany owner has explicitly excluded from the planned stack.

### Decision: adopt the isolation and review patterns; do not embed Orca

Useful patterns:
- Give each coding worker its own isolated Git worktree/branch.
- Use a coordinator to split work into bounded tasks and collect worker results.
- Require diff review, tests, and an approval gate before merge.
- Persist task state and allow remote jobs to continue if a client disconnects.

Do not make the Orca desktop app a required AIOS service: it is a developer-facing desktop product, not the lightweight headless backend the current repository needs. Do not require excluded coding-agent providers. Recreate only the provider-neutral orchestration and worktree safety patterns in AIOS, using its existing GitHub integration and approval system.

## 3. Reel: OpenHands, Dify, LibreChat

### OpenHands — adopt as an optional isolated coding-execution backend

Source: https://github.com/All-Hands-AI/OpenHands  
Documentation: https://docs.openhands.dev/sdk

OpenHands provides a composable Software Agent SDK, REST/WebSocket Agent Server, tools, MCP integration, and isolated workspaces/sandbox execution. The SDK documentation describes model-agnostic operation and support for local or remote execution. The SDK is MIT-licensed; check the license of each separate ecosystem repository before using it.

Use case in OpenCompany:
- Optional Developer-agent executor for code tasks only.
- Run inside a disposable, least-privilege workspace with no production secrets.
- Give it a task-scoped branch/worktree, not unrestricted repository or deployment access.
- Return a patch/PR and test report to AIOS.
- AIOS remains the authority for review, approvals, merge, and deployment.

Do not install or run it as part of the default API process yet. Its sandbox/container requirements are too heavy to assume on the current small/free hosting profile. First validate it locally or in a separate test environment and measure resource needs.

### Dify — do not adopt as the AIOS core

Source: https://github.com/langgenius/dify

Dify is a broad LLM application/workflow platform with its own frontend, API, workers, databases, Redis, plugin daemon, and runtime services. Its source license is Apache 2.0 with additional conditions, including restrictions on operating a multi-tenant environment without written authorization and frontend logo/copyright requirements.

It would duplicate AIOS task, workflow, and integration responsibilities and add substantial deployment complexity. Keep it as a reference for workflow authoring and RAG patterns only. Do not add it as a dependency or backend replacement.

### LibreChat — optional future operator interface, not the company runtime

Source: https://github.com/danny-avila/LibreChat

LibreChat is an MIT-licensed self-hosted AI chat platform. Its repository advertises multi-provider chat, agents, MCP, tools, and multi-user authentication.

It could become a future operator console, but it is not a substitute for AIOS's durable task queue, company memory, approval authority, execution audit, or unattended worker. It also introduces a separate application stack and configuration surface.

Do not deploy it now. First complete AIOS's API and task/approval lifecycle. Later, evaluate LibreChat strictly as an optional UI connected to AIOS APIs, with AIOS retaining all authorization and business state.

## 4. Target architecture after this evaluation

| Concern | System of record / preferred component | Boundary |
|---|---|---|
| Company tasks, state, approvals, audit | Existing AIOS FastAPI + database | Authoritative |
| Workflow orchestration | AIOS queue first; optional LangGraph adapter | Never bypass AIOS approval service |
| Model calls | Provider-neutral AIOS model adapter | Explicit provider config, no paid fallback |
| Provider discovery | Curated subset of free-LLM directory | Not keys; verify official terms |
| MCP tools | AIOS allowlisted MCP registry | Scoped credentials, tool-level approval |
| Coding execution | Optional OpenHands SDK/server | Isolated disposable workspace |
| Parallel code changes | Git worktrees / separate branches | No shared mutable working tree |
| Operator chat UI | Existing API initially; LibreChat optional later | UI is not source of truth |
| Dify / Orca | Design references only | No required runtime dependency |

## 5. Integration order

1. Fix the current worker service's missing runtime imports before enabling it.
2. Implement and test the provider-neutral model adapter and a curated provider catalogue.
3. Demonstrate a real model call using an owner-configured free-tier key or documented keyless endpoint; redact secrets.
4. Implement agent registry, task state handoff, bounded retries, and audit logging.
5. Add MCP registry with per-tool permissions and approval enforcement.
6. Add optional LangGraph orchestration over the AIOS task/approval services.
7. Pilot OpenHands in an isolated developer sandbox and return a patch for human review.
8. Add parallel worktree execution and CI-based review.
9. Consider LibreChat only after the AIOS APIs stabilize.

## 6. Acceptance criteria

- Provider status reports configured/disabled without exposing API keys.
- A real test request reports provider, model, latency, token usage when available, and failure category.
- No request is sent to a paid endpoint without explicit configuration and approval.
- Provider rate limits do not trigger uncontrolled account rotation.
- Developer-agent code changes are isolated and cannot reach production secrets.
- Parallel workers cannot overwrite each other's branch/worktree.
- A denied or missing approval prevents merge, deploy, publishing, spending, and customer commitments.
- Restarting the worker does not lose task state or duplicate external side effects.
- AIOS remains usable if OpenHands, Dify, LibreChat, Orca, or LangGraph is absent.

## Source notes

- Free LLM directory: https://github.com/mnfst/awesome-free-llm-apis
- Orca: https://github.com/stablyai/orca
- OpenHands SDK docs: https://docs.openhands.dev/sdk
- OpenHands overview: https://docs.openhands.dev/overview/introduction
- Dify license: https://github.com/langgenius/dify/blob/main/LICENSE
- LibreChat: https://github.com/danny-avila/LibreChat
