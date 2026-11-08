# Research & Technology Discovery Pipeline

Status: implementation specification; not yet an operational feature.

## Purpose

Continuously discover candidate GitHub projects and AI infrastructure resources, evaluate them against the AIOS requirements, and present evidence-backed recommendations in the owner dashboard. Discovery must never install, connect, publish, spend money, or change production automatically.

## Inputs

- GitHub repository search results and repository metadata.
- Maintained resource catalogues (including free-ai-tools and awesome-selfhosted).
- Official vendor documentation for API limits, pricing, data handling, and commercial-use terms.
- Existing AIOS requirements and integration inventory.

Third-party lists are discovery indexes, not proof that a service is free, safe, maintained, or suitable.

## Candidate record

Each candidate must retain:
- canonical repository or vendor URL;
- name, description, category, and proposed AIOS capability;
- source and time discovered;
- license and commercial-use status (unknown until verified);
- archived status, last-pushed timestamp, stars, and open issue/maintenance signals where available;
- required credentials, permissions, hosting, and runtime dependencies;
- cost model, free-tier limits, and evidence URL/date;
- security/privacy notes;
- compatibility assessment and test evidence;
- recommendation state: discovered, needs-review, approved-for-sandbox, rejected, or integrated.

Unknown values must remain explicitly unknown; never infer that a tool is free or commercially usable from a directory badge.

## Evaluation gates

1. **Identity and provenance:** canonical project/vendor and source links.
2. **Maintenance:** archived flag, recent activity, release history, unresolved critical issues.
3. **License and terms:** code license, model/API terms, commercial-use permission, attribution obligations.
4. **Cost:** free quota, card requirement, overage behavior, rate limits, and recurring infrastructure cost.
5. **Security:** secret handling, permissions requested, dependency health, data retention and training terms.
6. **Compatibility:** Python/runtime support, deployment footprint, API protocol, MCP compatibility, and fit with the current AIOS architecture.
7. **Sandbox test:** reproducible smoke test with synthetic data and no production credentials.
8. **Owner decision:** only the owner may approve integration or any consequential action.

## Owner dashboard requirements

Provide a Discovery page with:
- latest scan timestamp and source coverage;
- candidate table with status, category, maintenance, license, cost, and confidence;
- evidence drawer showing URLs and verification dates;
- filters for LLM APIs, MCP servers, agent frameworks, RAG/storage, self-hosting, and developer tools;
- actions: inspect, approve for sandbox, reject, and request re-check;
- visible run logs and failed checks.

Do not expose provider secrets in candidate details or logs.

## API and worker acceptance criteria

- Search and refresh operations are authenticated.
- Scans are queued and executed by a durable worker, not inside a request handler.
- Each scan has an ID, status, timestamps, source list, result count, and error details.
- Retries are bounded; stale leases recover; duplicate candidates are deduplicated by canonical URL.
- Rate limits and source terms are respected.
- Every claim is traceable to evidence and a verification timestamp.
- The worker can run in a clean environment with documented dependencies.
- CI covers successful scans, upstream failure, rate limiting, malformed metadata, duplicate detection, and approval boundaries.
- No install, deployment, purchase, publication, or production change occurs from discovery approval alone; integration requires a separate explicit owner approval.

## Current repository blockers found during audit

- The current README describes a starter API and says external providers, background workers, ecommerce, and social integrations are not connected.
- The current tree does not contain the modules imported by `src/ai_os/worker_service.py` (`agent_runtime`, `model_adapter`, and `worker`), so that worker entry point is not runnable from the checked-in tree.
- The current tests cover health, task creation, approval decisions, and API-key checks; they do not prove model calls, agent execution, scheduling, discovery, dashboard behavior, or external integrations.
- The roadmap marks the dashboard and background worker as pending. No owner-dashboard frontend is present in the checked-in tree.

## Delivery sequence

1. Repair or remove the currently dangling worker entry point; add a clean-start worker test.
2. Implement persistent discovery scan/candidate tables and typed schemas.
3. Add a provider-neutral GitHub discovery adapter with bounded rate limits and provenance.
4. Add deterministic evaluation gates; unknown cost/license/security facts fail closed to review.
5. Add authenticated owner-facing API endpoints and a visible dashboard page.
6. Add sandbox-only integration tests and CI coverage.
7. Connect a scheduled scan only after the owner can inspect results and disable it.

## Definition of done

The feature is not complete when a unit test passes. It is complete only when a real scan runs against public sources, produces inspectable candidates with evidence, survives worker restart, appears in the owner dashboard, and cannot perform consequential actions without explicit approval.
