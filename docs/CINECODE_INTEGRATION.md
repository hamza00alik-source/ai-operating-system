# Cinecode Integration Design

## Decision
Evaluate Cinecode as an optional, locally executed creative-production engine behind OpenCompany's existing video-job boundary. Do not make Cinecode the application architecture, copy its entire codebase into the API service, or replace the existing LongCat worker.

Upstream: https://github.com/sarpstar/cinecode

The inspected upstream repository is public and MIT-licensed. Preserve its LICENSE and attribution notices in any redistributed copy or derivative. Re-check the upstream license, dependency licenses, model/voice licenses, and asset-specific terms before each release.

## What the inspected project provides
Cinecode is an agent-operated filmmaking toolkit, not a hosted video-generation API. Its documented workflow uses an AI coding agent with local tool execution to create a film project, write scripts and scene code, render frames in headless Chrome, design/mix sound, run quality checks, and deliver an MP4.

Documented outputs include short films and animations; researched long-form documentaries and explainers; product and advertising films in 9:16, 1:1, and 16:9; music videos synchronized to a supplied track; and edits of user-supplied footage. It documents Quick and Film modes, creative approval checkpoints, draft revisions, independent review, loudness mastering, and source/licence tracking for external assets.

## Runtime requirements and constraints
The upstream README documents:
- An AI coding agent that can run local tools. Claude Code and Cursor are primary documented paths; Codex and Antigravity are also mentioned as community-tested.
- Node.js 22+, Python 3.9+, FFmpeg, Chrome/Chromium/Edge, a GPU Chrome can use, and sufficient disk.
- Quick mode needs hundreds of MB of working space; Film mode can need several GB.
- Rendering and mixing can work offline after required libraries/assets are cached, but research and some external asset/font/library retrieval require network access.
- Narration may require a user-provided provider key or an optional local voice model. "No paid service required" does not mean every optional narrator, asset, model, or compute path is free.

These requirements make Cinecode unsuitable for execution inside the FastAPI request process and unsuitable for the owner's Android phone as the render host. It should run on a separately provisioned, owner-managed workstation or worker with the required agent CLI and tools.

## Integration boundary
OpenCompany remains responsible for brief creation, provider selection, explicit cost/resource estimate and approval, idempotent job creation, worker authentication and leases, progress, cancellation and bounded retries, private artifact storage and owner review, and separate publishing approval.

Cinecode remains responsible for the local filmmaking workflow and render pipeline. The AIOS API must not accept arbitrary shell commands, arbitrary local paths, agent prompts that can escape the project workspace, or raw worker credentials.

## Proposed production flow
1. A creative/research workflow creates a structured video brief, script, target platform, aspect ratio, duration, style, audio plan, and asset/licence constraints.
2. AIOS creates a Cinecode job in `awaiting_approval` with an idempotency key, explicit cost basis, and budget ceiling.
3. The owner approves generation separately from approving the brief. Unknown costs are not represented as zero.
4. A separately deployed Cinecode worker claims only approved jobs for provider `cinecode`.
5. The worker validates its local environment, uses a pinned/verified Cinecode release, creates a fresh isolated project directory, and runs only a fixed supported agent adapter (no user-controlled command string).
6. Cinecode follows its own creative checkpoints. AIOS records stage/progress metadata and the worker maintains the AIOS lease.
7. The worker validates the final MP4 (container, size, duration, dimensions, audio stream) and uploads it to AIOS's private artifact endpoint.
8. The owner reviews the finished asset. Publishing or scheduling requires a separate approval and a separate platform integration.

## Agent execution design
Cinecode's core dependency is an agent that can operate local tools. AIOS's current bounded agent runtime is text-only and has no shell, filesystem, browser, or MCP tools. Therefore a Cinecode worker cannot be implemented safely by merely passing a Cinecode prompt to the existing LLM gateway.

An experimental adapter now exists at `workers/cinecode_worker.py`. It invokes the installed Codex CLI with fixed arguments (`codex exec`, `workspace-write`, `--ask-for-approval never`, `--ignore-user-config`, `--ephemeral`, and JSONL output), a per-job workspace, and a pinned clean Cinecode checkout. It does not accept a user-supplied executable or shell command. The creative brief is still untrusted input and the agent can execute commands inside its workspace; the Codex sandbox is not a complete security boundary.

Implemented worker controls:
- Non-interactive Codex CLI invocation with machine-readable JSONL output.
- Fresh UUID-named workspaces, with Git metadata, symlinks, local environment files, and secret/config directories excluded from the copy.
- AIOS owner and worker credentials filtered out of the Codex subprocess environment.
- Lease heartbeats, owner-cancellation checks, process timeout, bounded retry reporting, and cleanup.
- MP4 validation with ffprobe and streamed upload to the private AIOS artifact endpoint.
- A pinned upstream commit check and clean working-tree check before the worker starts.

Still required before production:
- Dedicated OS account/container/VM with no access to unrelated files or application secrets. Workspace-write alone is not a substitute for this.
- Host firewall/network policy and review of all installed Codex CLI/MCP configuration.
- Real CLI authentication/usage verification, Chrome/GPU compatibility, and end-to-end render and artifact-delivery tests on the actual worker host.

The worker is disabled by default and requires explicit execution and billing-confirmation environment gates. Do not enable it while the cost of the selected Codex account or other optional services is unknown.

## Provider contract
The existing provider-neutral video queue should expose a Cinecode provider with the same lifecycle as other engines:
- `capabilities()`: installed version, supported modes, formats, agent adapter, local tools, disk/GPU health and worker heartbeat.
- `estimate(job)`: local resource estimate, optional third-party/API usage, storage estimate and cost basis. Unknown remains unknown.
- `submit(job)`: only after owner approval and policy checks; return provider job ID.
- `status(provider_job_id)`: stage, safe progress, queued/running/succeeded/failed/cancelled.
- `fetch_result(provider_job_id)`: private artifact URI and validated media metadata.
- `cancel(provider_job_id)`: best-effort cancellation with auditable outcome.

Cinecode and LongCat must remain separate providers. A Cinecode failure must never silently fall back to a hosted GPU or paid API.

## Cost and approval policy
- Local execution may avoid a hosted GPU bill, but electricity, hardware wear, storage, bandwidth, model/API use, and maintenance still have costs.
- No cloud GPU, paid narrator, paid image/video generator, paid asset source, API credit purchase, or auto-top-up is enabled by default.
- Every paid or metered component needs an explicit estimate and approval before use.
- A generation approval is not a publishing approval.
- If cost or licensing cannot be established, stop that component and report the uncertainty.

## Security and privacy
- AIOS authenticates workers with provider-specific secrets: `VIDEO_WORKER_TOKEN` for LongCat and `VIDEO_CINECODE_WORKER_TOKEN` for Cinecode. Send the matching `X-Video-Provider` header on every worker request. Never reuse the same secret across providers.
- The claim request's provider must match the authenticated `X-Video-Provider` identity; changing the request body cannot switch a worker's authority.
- Use a dedicated OS account or container/VM for the worker, not the API process.
- Do not mount the AIOS repository, deployment secrets, home directory, or unrelated customer files into the render workspace.
- Allow only explicit input assets for each job.
- Keep worker and provider secrets server-side; never place them in film project files, Git, logs, prompts, or artifacts.
- Keep artifacts private and owner-authenticated.
- Enforce input/output file size and media-duration limits.
- Record asset URLs, licences, and attribution in the job deliverable.
- Do not upload private footage or customer data to external services without separate owner approval.

## Deployment profiles
### Profile A — no Cinecode worker (safe default)
AIOS can still create briefs, scripts, storyboards, shot lists and approval requests. Cinecode jobs remain unavailable until a worker is registered. No install, compute allocation, external call, or cost occurs.

### Profile B — owner-managed workstation
Preferred initial route: a dedicated desktop/workstation owned and controlled by the user. Install the required tools and a supported coding-agent CLI after a setup review. Keep the worker off the Android phone. The workstation connects outbound to the AIOS HTTPS API and polls only its authenticated queue.

### Profile C — hosted worker
Consider only after isolation, cost estimation, provider terms, persistent storage, and cancellation are verified. Hosted compute is not free and is disabled by default.

## Acceptance tests before calling Cinecode integrated
1. AIOS boots and all existing tests pass with no Cinecode install or worker.
2. Capability status clearly reports Cinecode unavailable when no worker is connected.
3. A Cinecode job cannot be claimed before owner approval.
4. Provider routing cannot cross-claim LongCat jobs.
5. Repeated submissions with the same idempotency key do not create duplicate renders.
6. Worker commands are fixed/allowlisted; prompt text cannot inject arbitrary shell commands or paths.
7. Job workspaces are isolated and cleaned according to retention policy.
8. Secrets do not appear in prompts, logs, Git, or artifacts.
9. Cancellation, timeout, worker restart, lease expiry, and bounded retry are tested.
10. MP4 metadata and size are validated before private artifact storage.
11. A failed Cinecode worker never triggers paid or hosted fallback.
12. Generated output remains private until owner review; publishing remains a separate approval.
13. A real end-to-end local render is completed on the intended worker hardware and its logs, resource use, and output are reviewed.

## Current status
- Upstream repository and documentation inspected.
- Existing AIOS video queue, owner approval, budget gate, authenticated worker lease protocol, and private MP4 artifact path inspected.
- Existing AIOS LongCat worker remains a separate optional provider.
- Provider-scoped job claims and provider-specific worker heartbeat status now accept `cinecode` separately from `longcat-video`.
- Provider-specific worker credentials now prevent a LongCat worker from authenticating as Cinecode and vice versa; expired lease recovery is provider-scoped.
- The Owner Console now has read-only readiness, queue, progress, and completed MP4 artifact links for both providers.
- Focused video integration tests have passed on the CI branch; the full repository suite still has unrelated failures in `tests/test_opencompany_app.py`.
- The experimental local Codex worker implementation and setup guide are now in the branch. Focused CI passed for the worker's unit tests on the implementation commit; later hardening commits still need a fresh CI run.
- The worker is not deployed, and no intended workstation/VM has been provisioned or authenticated. A real Cinecode render and end-to-end MP4 delivery remain unverified.
- The full repository suite currently has 30 failures in the separate `tests/test_opencompany_app.py` suite (165 passed). These failures are outside the Cinecode files but prevent a green full-suite result.
- Cinecode remains unavailable for production until the host isolation, billing, actual rendering, and latest CI gates are verified.
