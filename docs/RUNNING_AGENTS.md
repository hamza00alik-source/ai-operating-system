# Running specialist agents

## What "running" means here

The 283 Agency Agents entries are specialist role profiles, not 283 separate
installed AI models or independent processes. The runtime starts a bounded worker
process and assigns each persisted company-run step to its selected specialist.
The specialist receives its full profile and task, generates a structured report,
and reports it to the CEO. Dependencies are respected: downstream specialists
are not scheduled until their prerequisites complete.

## Model requirement and zero-cost default

The worker does not include an AI model. A model endpoint must be deliberately
configured through the existing provider-neutral OpenAI-compatible adapter.
Nothing is enabled by default, no provider is selected, and there is no silent
paid fallback. A local inference server can be used without an API key; the
owner must verify the host can run the chosen model. A hosted endpoint may incur
charges or have changing free-tier terms, so it must not be assumed free.

The Agency Agents repository supplies role instructions; it does not itself
supply a free inference engine. A profile alone cannot reason or execute tasks.

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

Then start the persistent worker process:

```bash
python -m ai_os.worker_service
```

Create a company objective through POST /ceo/plan. The worker discovers
dependency-ready steps, dispatches them into the durable queue, executes them,
and stores authenticated specialist reports for CEO review. Keep the worker
running as a separate process; stopping it pauses work without losing queued
jobs. Restarting resumes queued jobs subject to the queue's bounded retry and
lease policy.

## Safety limits

- Specialists have no shell, browser, WooCommerce, social, email, payment, or
  deployment tools in this first runtime.
- Model output is untrusted report data, never an executable command.
- The runtime only writes internal reports and audit events.
- Publishing, sending customer messages, spending, refunds, purchases,
  production changes, and public deployment remain disabled.
- Owner approval primitives are not yet wired to external execution.
- Use one worker process initially. Multiple workers require a later concurrency
  and recovery review.
