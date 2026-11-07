# Running specialist agents

## What "running" means here

The 283 Agency Agents entries are specialist role profiles, not 283 separate
installed AI models or independent processes. The runtime starts a bounded worker
process and assigns each persisted company-run step to its selected specialist.
The specialist receives its full profile and task, generates a structured report,
and reports it to the CEO. Dependencies are respected: downstream specialists
are not scheduled until their prerequisites complete.

## Model requirement and zero-cost default

The worker does not include an AI model. An inference backend must be deliberately
configured. The default is the provider-neutral OpenAI-compatible HTTP adapter;
an optional owner-configured local CLI adapter is also available.
Nothing is enabled by default, no provider is selected, and there is no silent
paid fallback. A local inference server can be used without an API key; the
owner must verify the host can run the chosen model. A hosted endpoint may incur
charges or have changing free-tier terms, so it must not be assumed free.

The Agency Agents repository supplies role instructions; it does not itself
supply a free inference engine. A profile alone cannot reason or execute tasks.

## Optional authenticated CLI backend

The CLI backend can invoke an already-authenticated local command without an API
key. It is opt-in and does not assume that a particular CLI is installed or free.
For the `agy` command previously used in this project, the argument shape below
matches the observed prompt-mode invocation; its structured response format has
not yet been verified against the installed CLI, so a real runtime smoke test is
still required before relying on it:

```bash
export AI_OS_MODEL_BACKEND=command
export AI_OS_MODEL_COMMAND=agy
export AI_OS_MODEL_COMMAND_ARGS='["-p", "{prompt}", "--output-format", "json"]'
export AI_OS_MODEL_NAME=agy-cli
# Explicitly attest that this CLI profile has no shell/browser/file/action tools.
export AI_OS_MODEL_COMMAND_NO_TOOLS_CONFIRMED=true
export AI_OS_MODEL_ENABLED=true
```

The adapter uses an argument array with `shell=False`, a bounded timeout, and
strict JSON parsing. It never accepts shell command strings from model output.
However, a CLI may have its own browser, shell, file, or network tools enabled;
configure and verify a prompt-only/no-tools CLI profile before enabling this
backend, then explicitly set `AI_OS_MODEL_COMMAND_NO_TOOLS_CONFIRMED=true`.
This is an owner attestation, not an independent sandbox or technical proof.
The operating system cannot sandbox permissions granted by that CLI.
CLI execution may also use the network and may be subject to the CLI provider's
terms or quotas. Keep this backend disabled until the CLI's permissions and
output contract have been checked.

## Enable the worker

After the GitHub implementation is reviewed and the project is installed on a
host with a reachable compatible model endpoint, configure the endpoint and
explicitly opt in:

- AI_OS_MODEL_BASE_URL: compatible endpoint URL (HTTPS for remote endpoints;
  localhost HTTP is permitted).
- AI_OS_MODEL_NAME: model identifier.
- AI_OS_MODEL_API_KEY: optional; leave unset for a local endpoint.
- AI_OS_MODEL_ENABLED=true: explicit opt-in.
- AI_OS_AGENT_SIGNING_KEY: random secret of at least 32 characters.
- AI_OS_API_TOKEN: owner API token of at least 32 characters.

Start the worker service as a separate, long-lived process (use your host's
process manager, such as systemd or an equivalent restart policy):

```bash
python -m ai_os.worker_service
```

The service starts in the persisted `stopped` state and waits without claiming
jobs until the owner changes its desired state. The API exposes owner-authenticated
controls:

- `GET /worker/status` — desired state, live worker heartbeats, and queue counts.
- `POST /worker/start` — allow the worker process to schedule and claim jobs.
- `POST /worker/pause` — stop claiming new jobs; an already claimed job is
  allowed to finish.
- `POST /worker/resume` — resume scheduling and job claims.
- `POST /worker/stop` — return to the stopped/idle state without deleting jobs.

These API calls update persisted desired state; they do not spawn or terminate an
operating-system process. The separately hosted worker service must already be
running. Use the host process manager to launch it on boot and restart it after
host/process failure. If the API and worker use separate containers, they must
share the same persistent SQLite database volume. Keep one worker process for
now; parallel replicas are intentionally not enabled.

Once the owner starts the worker, create a company objective through
`POST /ceo/plan`. When model execution is explicitly enabled, the worker
discovers dependency-ready steps, dispatches them into the durable queue,
executes them, and stores authenticated specialist reports for CEO review.
The queue renews the active job lease during long-running handlers; after a
process crash, expired leases are recovered through the bounded retry policy.
With model execution disabled, the process can still handle eligible local
jobs, but it does not schedule model-backed specialist steps.

## Safety limits

- Specialists have no shell, browser, WooCommerce, social, email, payment, or
  deployment tools in this first runtime.
- Model output is untrusted report data, never an executable command.
- The runtime only writes internal reports and audit events.
- Publishing, sending customer messages, spending, refunds, purchases,
  production changes, and public deployment remain disabled.
- Owner approval primitives are not yet wired to external execution.
- Use one worker process initially. Parallel replicas are not enabled until
  cross-process concurrency and recovery are separately validated.


## Failed work and dependency propagation

A specialist report with `status=blocked` is retained for the CEO. Pending
downstream steps that depend on that blocked step are marked blocked with a
system-generated explanation; they are not silently left pending. Independent
workstreams remain eligible to run. When a specialist job exhausts its durable
queue retry allowance, the worker marks the assigned step blocked and applies
the same dependency propagation. A company run becomes `blocked` only after
all its steps are terminal and at least one step is blocked; otherwise it stays
active while independent work remains. These transitions are covered by
mocked runtime tests and do not require a live model provider.
