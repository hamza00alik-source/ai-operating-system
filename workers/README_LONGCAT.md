# Optional LongCat GPU worker

The OpenCompany API and dashboard do **not** require this worker. Without it, briefs, approvals, queued jobs, job history, and cancellation remain available; generation simply waits for a worker.

## Supported first release

- LongCat-Video text-to-video only.
- One CUDA GPU process per worker.
- 480p-class output (832×480 default), MP4, up to 129 frames.
- The approved prompt is passed to the LongCat pipeline. This deliberately avoids the upstream demo script's hardcoded sample prompt.
- Generated MP4 is uploaded to the OpenCompany API and stored in its configured artifact directory.
- Image-to-video, continuation, Avatar, multi-GPU execution, 720p refinement, and distributed worker pools are not enabled by this adapter.

## 1. Deploy the API independently

Set these server-side environment variables on the OpenCompany API service:

- `VIDEO_WORKER_TOKEN`: a strong random secret shared with the GPU worker. Generate one with `openssl rand -hex 32`; never commit it.
- `PUBLIC_API_BASE_URL`: the public HTTPS origin of the API, e.g. your Railway API domain (no trailing slash).
- `VIDEO_ARTIFACT_DIR`: a persistent mounted volume path, e.g. `/data/video-artifacts`. Mount a Railway volume there before relying on generated artifacts; the container filesystem may be ephemeral.
- Keep the existing `AI_OS_DATABASE_URL` on persistent storage too, because job records and lease state live in SQLite.

The API's worker routes reject requests without the worker secret and a valid per-job lease token. Owner-only routes still use the existing owner authentication.

## 2. Prepare a separate CUDA machine

Use a Linux machine with a compatible NVIDIA CUDA GPU and sufficient VRAM. LongCat-Video is a 13.6B-parameter model; open-source weights do not make GPU compute free. Do not enable a paid GPU host or incur a download/compute charge without a separate owner decision.

Use the upstream installation instructions and its Python 3.10 environment. Install the pinned CUDA/PyTorch and FlashAttention versions from the LongCat-Video README, then install its `requirements.txt`. Clone the upstream repository (or use the user's tracked fork) outside the OpenCompany API container and download the official `meituan-longcat/LongCat-Video` weights to a local directory. Check the current upstream model and dependency licenses before redistribution.

## 3. Configure and start

From the OpenCompany checkout on the GPU machine, set:

```bash
export OPENCOMPANY_API_URL="https://YOUR-OPENCOMPANY-API"
export VIDEO_WORKER_TOKEN="THE_SAME_RANDOM_SECRET_AS_THE_API"
export VIDEO_WORKER_ID="longcat-gpu-01"
export LONGCAT_REPO_DIR="/opt/LongCat-Video"
export LONGCAT_CHECKPOINT_DIR="/models/LongCat-Video"
export LONGCAT_OUTPUT_DIR="/data/longcat-output"
export VIDEO_JOB_LEASE_SECONDS="180"
```

Run one process on one GPU:

```bash
torchrun --nproc_per_node=1 workers/longcat_worker.py
```

The worker loads model weights once, polls the authenticated queue, claims only owner-approved jobs, renews its lease during inference, observes cancellation requests, and reports success/failure. Do not run multiple worker processes against the same GPU unless separate GPU capacity is available.

## 4. Create and approve a job

Create a video job with `POST /video/jobs`, including a stable idempotency key, explicit cost estimate, approved budget ceiling, and cost basis. Then use `POST /video/jobs/{id}/decision` with `approved`. Approval queues the job; it does not itself start generation. The worker starts only after it claims the queued job.

Supported optional parameters:

- `width`: 832 (or 640)
- `height`: 480 (or 384)
- `num_frames`: 17–129, where the value is 4n+1
- `num_inference_steps`: 20–60 (default 50)
- `fps`: 8–30 (default 15)
- `guidance_scale`: 1–8 (default 4)
- `seed`: integer
- `negative_prompt`: string

## 5. Monitoring and cancellation

- `GET /video/status` reports recent worker presence.
- `GET /video/jobs` and `GET /video/jobs/{id}` report queue and execution state.
- `GET /video/jobs/{id}/events` provides the audit trail.
- `POST /video/jobs/{id}/cancel` cancels queued jobs immediately or requests cancellation for a running job.
- Successful artifacts are available from `GET /video/artifacts/{id}` with owner authentication.

Cancellation is cooperative: a LongCat inference call already executing cannot be safely interrupted by this initial adapter. The worker stops before artifact upload/reporting when it observes cancellation. A lost heartbeat causes the worker to avoid reporting success; lease expiry makes the job eligible for bounded retry. A persistent API artifact volume is required to preserve MP4s across API redeployments.

## Security notes

The shared worker secret authenticates the worker process; each claim also receives a unique lease token. Only the token hash is persisted. A worker cannot report progress or results for another job, and an expired lease cannot complete a job. Worker routes never accept shell commands or arbitrary file paths. Artifact upload is limited to MP4 containers and 300 MB. Publishing remains a separate workflow and is not triggered by generation.
