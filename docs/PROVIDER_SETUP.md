# Free model providers and local database setup

This guide configures the existing bounded worker for no-cost inference. It does not create provider accounts, provision a host, or verify that a provider account is on a free plan. Model execution and external actions remain disabled until explicitly enabled.

## Default free-only controls

The runtime defaults to `AI_OS_FREE_ONLY=true`. In this mode, only the exact Gemini or Groq preset endpoints, or the exact localhost Ollama endpoint, may run. The model ID must also appear in `AI_OS_FREE_MODEL_ALLOWLIST`. Gemini and Groq additionally require an API key and `AI_OS_MODEL_FREE_TIER_CONFIRMED=true`, which is an owner attestation—not an automated billing check. Confirm the provider account, model access, quotas, and billing state yourself before setting it. The worker does not silently switch providers or retry jobs after a provider quota error.

Keep `AI_OS_MODEL_ENABLED=false` until the owner approves a low-sensitivity smoke test. Never commit real API keys; store them only in the private runtime environment. Keep `AI_OS_EXTERNAL_ACTIONS_ENABLED=false`. Model output is untrusted, and the worker can create internal reports only; it cannot publish, message customers, spend, or deploy.

## No-cost database: SQLite

SQLite is the default and requires no database account or network service. The default file is `./data/ai_os.db`; the application creates the parent directory. For a hosted runtime, point `AI_OS_DATABASE_URL` at a persistent writable disk, for example:

```dotenv
AI_OS_DATABASE_URL=sqlite:////srv/ai-os/data/ai_os.db
```

The API and worker must use the same SQLite file. A host with an ephemeral disk can lose records when replaced, and a local snapshot on the same machine is not disaster recovery. Back up verified database copies outside the live path; see [the backup and restore instructions](OPERATIONS_PLAYBOOK.md#backup-and-restore). This project supports SQLite here, not an automatically provisioned cloud database.

## Gemini through Google AI Studio

Choose a model that your AI Studio account currently marks as Free Tier. Google documents free input and output for eligible models, but model access and quotas vary by account. Google says content submitted on its Free Tier may be used to improve products; do not send confidential business or customer data unless the owner has reviewed and accepted the current terms. The app cannot inspect the account's billing plan. See [Gemini pricing](https://aistudio.google.com/docs/pricing), [rate limits](https://aistudio.google.com/docs/rate-limits), and [OpenAI compatibility](https://aistudio.google.com/docs/openai). The longer account setup and data-terms review is in [the Gemini-specific guide](PROVIDER_GEMINI_SETUP.md).

Example private environment (replace the model with the exact free model available to your account):

```dotenv
AI_OS_MODEL_ENABLED=false
AI_OS_MODEL_BACKEND=openai_compatible
AI_OS_MODEL_PROVIDER=gemini
AI_OS_MODEL_NAME=gemini-3.8-flash
AI_OS_MODEL_API_KEY=<private-key>
AI_OS_MODEL_FREE_TIER_CONFIRMED=true
AI_OS_FREE_ONLY=true
AI_OS_FREE_MODEL_ALLOWLIST=gemini-3.8-flash
```

The Gemini preset supplies `https://generativelanguage.googleapis.com/v1beta/openai/`. The sample model is illustrative, not a guarantee of free availability. Do not add billing or enable a paid tier for this setup.

## Groq developer free plan

Use Groq only if the selected model is currently included in the account's free plan. Limits vary by model and account; check the provider console and data terms. See [Groq rate limits](https://console.groq.com/docs/rate-limits), [OpenAI compatibility](https://console.groq.com/docs/openai), and [structured outputs](https://console.groq.com/docs/structured-outputs).

```dotenv
AI_OS_MODEL_ENABLED=false
AI_OS_MODEL_BACKEND=openai_compatible
AI_OS_MODEL_PROVIDER=groq
AI_OS_MODEL_NAME=openai/gpt-oss-20b
AI_OS_MODEL_API_KEY=<private-key>
AI_OS_MODEL_FREE_TIER_CONFIRMED=true
AI_OS_FREE_ONLY=true
AI_OS_FREE_MODEL_ALLOWLIST=openai/gpt-oss-20b
```

The Groq preset supplies `https://api.groq.com/openai/v1`. Confirm the exact model is free in your own account. If its quota is exhausted, the job stops; it does not upgrade or fall back to another provider.

## Local Ollama

Ollama can run an open model on your own computer without a remote inference API key or provider bill. Hardware, electricity, storage, and uptime are still required. The default free-only allowlist accepts Ollama only at `http://127.0.0.1:11434/v1`; keep it bound to localhost and do not expose its unauthenticated endpoint to the public internet. See [Ollama quick start](https://docs.ollama.com/quickstart) and [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility).

For example, after installing Ollama and downloading a model such as `gemma4:e2b`, set:

```dotenv
AI_OS_MODEL_ENABLED=false
AI_OS_MODEL_BACKEND=openai_compatible
AI_OS_MODEL_PROVIDER=ollama
AI_OS_MODEL_NAME=gemma4:e2b
AI_OS_MODEL_API_KEY=
AI_OS_FREE_ONLY=true
AI_OS_FREE_MODEL_ALLOWLIST=gemma4:e2b
```

The endpoint is inferred; no remote free-tier attestation is needed. An Android phone is not a reliable always-on worker and model host for this setup; use a suitable always-on computer.

## Controlled activation

Provider and database configuration are supplied through environment variables. After checking the account, model, usage limits, privacy terms, and persistent database path, request owner approval for one low-sensitivity test. Set `AI_OS_MODEL_MAX_REQUESTS_PER_STEP=1`, enable model execution only for the test, and create a harmless internal task with no customer data, credentials, or external-action request. Verify the provider/model recorded in the result, inspect provider usage, and disable inference again if the plan or behavior is unclear. `GET /models/status` reports readiness without contacting a provider.

Run the API and the separately managed worker on a suitable persistent host, both pointing to the same database. Start the worker with `python -m ai_os.worker_service`; owner-authenticated `POST /worker/start` allows it to process queued jobs. Worker controls do not start an operating-system process by themselves. Free cloud hosts may sleep or reclaim instances and may not offer persistent disk, so this is not yet an always-on production company deployment.
