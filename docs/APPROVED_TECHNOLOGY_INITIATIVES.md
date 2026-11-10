# Approved technology initiatives — implementation register

This register tracks the five initiatives approved for AIOS. It is an implementation and evidence boundary, not a claim that every upstream project is production-ready.

## Guardrails

- Keep the Owner Console, existing department registry, AI Brain, workflows, provider gateway, and SQLite database intact.
- Keep all work on a feature branch until owner review.
- No paid inference, purchases, subscriptions, public publishing, production deployment, or external customer actions.
- Provider "free" status is account-, model-, region-, and time-dependent. Unknown terms remain unknown.
- Local GPU workloads are optional research only; the current lightweight hosted service is not a video-generation workstation.

## 1. AI Model Intelligence Department

**Purpose:** maintain a source-attributed view of model providers and route only through existing owner-approved, free-confirmed gateway configurations.

Existing capability reused:
- discovery.py imports the CC0 free API evidence catalog into SQLite.
- llm_gateway.py performs guarded provider routing and free-confirmed failover.
- credentials.py encrypts owner-supplied provider credentials.

Next acceptance criteria:
- Store evidence age and primary-source references for each provider/model.
- Mark expired evidence as stale; never silently convert a stale free-tier claim into an eligible route.
- Keep account-specific live tests owner-triggered and report only the minimum required diagnostics.
- Maintain a model benchmark ledger only when the owner explicitly requests a test; do not issue background inference calls.

Status: added a read-only `/llm/intelligence` endpoint that summarizes configured providers, owner free-confirmation, eligibility, and blockers without network probes or inference. The `/discovery/provider-catalog` response now classifies evidence as recent, stale, or unknown using a conservative 30-day age threshold based on the catalog's `last_verified` date (source-access dates are fallback only). Each entry exposes its evidence age and explicitly remains ineligible for routing from the research catalog. This metadata does not override the existing gateway's separate owner-confirmation rules. An owner-only `/llm/benchmarks/run` endpoint now runs a fixed connection probe only after explicit free-only confirmation and only through the existing eligible gateway. Outcomes, latency, available token counts, and bounded error summaries are stored in SQLite; prompts and model responses are not persisted. `/llm/benchmarks` is a read-only owner-only history endpoint. No benchmark runs automatically; paid providers are rejected.

## 2. Notification Infrastructure

**Chosen direction:** Apprise as an optional delivery adapter, behind an AIOS-owned notification queue and approval boundary.

Required design:
- Persist notification intent and delivery state in SQLite.
- Default to disabled until an owner configures a destination.
- Permit internal operational alerts (worker failure, queue backlog, approval awaiting review) only after destination setup.
- Require explicit owner approval for customer-facing messages or messages that create commitments.
- Redact credentials and sensitive payloads from logs.
- Keep Apprise optional so core AIOS can install and run without it.

Status: SQLite notification queue and optional Apprise adapter implemented on the feature branch. Enqueueing never sends. Customer notifications remain pending until the linked owner approval is approved. Delivery is disabled unless the owner explicitly enables it and configures a destination. Apprise remains optional and is not installed by default. No notification has been sent.

## 3. Persistent Agent Execution

Existing runtime already persists task runs, events, steps, partial outputs, and retry state. Its API lifespan runs worker loops in-process. The standalone worker_service previously imported ai_os.worker and ai_os.model_adapter, which are absent from the current main-branch package. This branch repairs that entry point to call the existing discovery and agent queue functions and adds bounded retry backoff plus graceful SIGINT/SIGTERM shutdown.

Important remaining limitation:
- The current run_pending_once queue claims are not a distributed lease protocol. Run one worker process against one persistent SQLite database; do not scale to multiple replicas until atomic claims, lease renewal, stale-claim recovery, and retry limits are implemented and tested.
- A host restart may leave a run marked running; the current startup recovery marks interrupted runs failed for explicit owner retry. It does not silently replay model requests.

Status: standalone worker import/runtime path repaired with bounded process-level backoff and graceful shutdown. Agent runs and discovery scans now use atomic SQLite claims, worker-owned expiring leases, heartbeat renewal, ownership checks before committing results, and expiry-aware recovery. Expired/interrupted work is marked failed for explicit owner review; uncertain model/API work is never automatically replayed. Stale workers cannot renew expired leases or write final failure/completion state after ownership is lost. Coordination remains single-host SQLite only; this is not a distributed multi-host lease/fencing system.

## 4. AI Video Production Research — LongCat-Video

**Role:** future production research only. The project is a video-generation model/research codebase, not a lightweight hosted feature.

Before any integration:
- Verify upstream license and commercial-use rights for code, weights, and training data separately.
- Verify hardware, VRAM, storage, inference duration, and model download requirements.
- Benchmark locally with a tiny non-commercial sample only if compatible hardware and free compute are available.
- Keep generated video production outside the current hosted API until cost and capacity are proven.

Status: research track only; no weights downloaded, GPU provisioned, or video generated.

## 5. Cross-framework Development Research — Mitosis

**Role:** optional source-generation experiment for reusable UI components across supported frameworks.

Before integration:
- Identify one small, isolated component with no backend secrets or business logic.
- Compare generated output against the existing Owner Console and its mobile behavior.
- Add Mitosis only as a development dependency if a repeatable build/test case demonstrates value.
- Do not rewrite the existing Owner Console or introduce a second frontend toolchain without an owner-reviewed migration plan.

Status: research track only; no frontend migration or dependency added.

## Acceptance gates

A capability is not "complete" until its tests pass on the feature branch, limitations are documented, and the owner reviews the resulting pull request. A successful CI run proves code tests only; it does not prove live provider access, host persistence, or production deployment.
