# LongCat-Video Integration Design

## Decision

Treat `hamza00alik-source/LongCat-Video` as a tracked upstream fork and optional video-engine implementation, not as the OpenCompany application or its core architecture.

The fork currently has no code divergence from `meituan-longcat/LongCat-Video` on `main` (GitHub compare: `identical`, 0 commits ahead, 0 behind). Keep upstream model code isolated. OpenCompany owns job orchestration, approval, provider selection, cost controls, artifact records, and user experience.

## What the engine supports

The upstream project documents:
- Text-to-video.
- Image-to-video.
- Video continuation and long-video generation.
- Interactive video generation.
- Audio-driven avatar generation through the LongCat-Video-Avatar family, including Avatar 1.5.

The base video model has 13.6B parameters. The upstream quick start uses Python 3.10, PyTorch 2.6.0 with CUDA 12.4 wheels, FlashAttention 2, and a large model-weight download. These are GPU-server workloads, not Android-phone workloads.

## Integration boundary

Do not import LongCat's Python packages into the FastAPI application process. Run it as a separate, optional GPU worker/service. The OpenCompany API must remain usable when no GPU worker is installed or online.

Proposed flow:

1. The content workflow creates a video brief and script.
2. The owner reviews the brief and explicitly approves a generation job.
3. OpenCompany validates the selected engine, task type, input assets, duration/resolution, estimated resource class, and configured cost ceiling.
4. A queue stores a job with a stable ID and idempotency key.
5. A separately deployed LongCat worker claims the job and runs the matching upstream inference entrypoint.
6. The worker reports progress and a terminal result; OpenCompany stores metadata and an artifact reference, not model weights.
7. The owner reviews the rendered video. Publishing remains a separate approval and integration.

## Adapter contract (to implement)

Keep a provider-neutral contract so other engines can be added without changing the social/video workflow:

- `capabilities()`: engine availability, supported tasks, resolutions, audio modes, and worker health.
- `estimate(job)`: resource estimate and any known monetary charge; unknown cost must remain unknown, not be treated as zero.
- `submit(job)`: enqueue only after approval and cost policy checks; return a provider job ID.
- `status(provider_job_id)`: queued/running/succeeded/failed/cancelled plus safe progress metadata.
- `fetch_result(provider_job_id)`: return an artifact URI and validated media metadata.
- `cancel(provider_job_id)`: best-effort cancellation with auditable outcome.

Do not expose arbitrary shell commands, Python execution, filesystem paths, or raw worker credentials through the owner API.

## Cost and approval rules

- Open-source code and MIT-licensed model weights do not make GPU compute free.
- A local GPU worker may have no incremental cloud bill, but still has hardware, electricity, storage, and maintenance costs.
- A hosted GPU worker is disabled by default. Before enabling it, show provider, region, rate, expected runtime/cost, maximum spend, and whether storage/egress is charged.
- If cost cannot be established, block hosted execution pending owner review.
- No automatic paid fallback, auto-top-up, or unattended cloud provisioning.
- Approval to create a draft is not approval to run a GPU job; generation approval is a separate decision.
- Approval to generate is not approval to publish.

## Deployment profiles

### Profile A — no GPU available (current safe default)

OpenCompany continues creating briefs, scripts, prompts, shot lists, and editing plans. Jobs remain unsubmitted and visibly report that no LongCat worker is configured. No external service is called and no cost is incurred.

### Profile B — owner-managed GPU

The owner deploys the LongCat worker on a compatible machine. OpenCompany connects using a private service credential. This is the preferred path for controlling cost, subject to actual GPU compatibility and performance tests.

### Profile C — hosted GPU

A cloud GPU worker may be added later behind explicit per-job approval and a hard spending ceiling. This is not a free tier and must never be represented as free.

## Security and reliability requirements

- Keep Hugging Face tokens, worker credentials, and storage credentials in server-side secret storage only.
- Do not put model weights, generated videos, private inputs, or credentials in Git.
- Restrict worker ingress to authenticated OpenCompany requests.
- Validate file types, sizes, durations, and media metadata before queueing and after generation.
- Use job timeouts, bounded retries, idempotency, cancellation, and worker leases.
- Persist job events and owner decisions for audit.
- Keep input/output storage private by default; use expiring links for previews.
- Do not send customer or confidential media to third-party compute without a separate owner decision and appropriate provider review.

## License and provenance

The fork's checked-in LICENSE is MIT and retains Meituan copyright attribution. Preserve the upstream license and notices in any redistributed copy or derivative. Re-check upstream changes and any individual dependency/model license before each release. MIT does not grant Meituan trademark or patent rights.

## Acceptance tests before calling this integrated

1. OpenCompany boots and all existing workflows work with no LongCat package, weights, GPU, or credentials installed.
2. Capability health reports `unavailable` when the worker is offline without breaking the owner dashboard.
3. An unapproved job cannot be submitted.
4. A hosted job with unknown cost or no explicit budget ceiling is rejected.
5. A local-worker job cannot silently switch to a hosted provider.
6. Duplicate submit requests do not create duplicate generation jobs.
7. Failed, timed-out, cancelled, and successful jobs all persist auditable terminal states.
8. Result metadata is validated and the video remains private until owner review.
9. No generation result can trigger social publishing automatically.

## Current status

This document records the architecture decision and repository audit. It does not claim that a LongCat adapter, GPU worker, job queue, or video generation is implemented or operational yet.
