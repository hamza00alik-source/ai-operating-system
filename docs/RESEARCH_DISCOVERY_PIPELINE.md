# Research & Technology Discovery Pipeline

Status: operational MVP in the deployed FastAPI service; metadata discovery only.

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

## Current verified limitations

- Discovery searches public GitHub repository metadata only; it does not inspect source code, releases, advisories, vendor pricing pages, or API terms.
- The worker is an in-process thread in the API service and assumes one replica. Durable multi-replica leases and scheduled recurring scans are not implemented.
- Search requests use the unauthenticated public API unless `GITHUB_TOKEN` is configured. A token improves quota but is optional for public repositories.
- License metadata is not a complete commercial-use legal review. Cost, security, privacy, and provider free-tier terms remain unknown until checked against authoritative sources.
- Candidate approval is a review-state change only; it does not install, connect, or execute repository code.
- The test suite covers queueing and conservative metadata evaluation, but production end-to-end scans still need a live owner-triggered verification after deployment.

## Remaining delivery sequence

1. Run a live scan from the authenticated owner dashboard and verify completed scan records and persisted candidates.
2. Add repository README/source inspection with bounded file-size and request limits; treat all repository content as untrusted input.
3. Add authoritative vendor documentation checks for API pricing, free quotas, commercial-use terms, privacy, and security.
4. Add scheduled recurring scans only after scan controls, rate-limit handling, and worker restart behavior are proven.
5. Add sandbox compatibility tests before any integration is approved.

## Definition of done

The feature is not complete when a unit test passes. It is complete only when a real scan runs against public sources, produces inspectable candidates with evidence, survives worker restart, appears in the owner dashboard, and cannot perform consequential actions without explicit approval.
