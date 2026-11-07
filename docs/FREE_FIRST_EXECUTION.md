# Free-first execution model

The operating system is useful without a paid model API: it can create local work packets, store company records in SQLite, and keep jobs queued until inference is deliberately enabled. A role profile is not a model; automatic specialist execution requires an available inference backend and a separately running worker process.

## Local workflow and persistence

`GET /runtime` reports execution modes, `GET /models/status` checks configuration without contacting a provider, and `POST /work-packets` prepares prompts locally. SQLite is the default database at `./data/ai_os.db`; the API and worker must use the same persistent writable file. The application does not provision or replicate a cloud database. See [provider and database setup](PROVIDER_SETUP.md) and [database backup instructions](OPERATIONS_PLAYBOOK.md#backup-and-restore).

## Free model options

The runtime includes OpenAI-compatible presets for Gemini through Google AI Studio and Groq, plus local Ollama. Strict free-only mode defaults to on and accepts only the exact Gemini/Groq preset endpoints or localhost Ollama. The chosen model ID must be explicitly added to `AI_OS_FREE_MODEL_ALLOWLIST`. Gemini and Groq require an API key and the owner's `AI_OS_MODEL_FREE_TIER_CONFIRMED=true` attestation; the app cannot verify billing or account eligibility. See the [Gemini account guide](PROVIDER_GEMINI_SETUP.md).

Free cloud quotas and model eligibility change. Provider outages and quota errors stop jobs rather than trigger retries or a paid fallback. Google AI Studio's free-tier content terms may permit submitted content to be used to improve products; do not send confidential business or customer data without the owner's review and acceptance of current terms. Local Ollama avoids a model-provider inference bill but still uses hardware, electricity, storage, and host uptime.

## Cost and action controls

`AI_OS_MODEL_ENABLED=false` is the default, so no model is contacted until a private runtime explicitly enables it. Strict free-only mode blocks generic or unlisted providers, and the `AI_OS_EXTERNAL_ACTIONS_ENABLED=false` default keeps the worker limited to internal reports. Model output is untrusted and cannot approve or perform spending, publishing, customer contact, production changes, or deployment.

## Current limitations

Free API plans and free cloud hosts do not guarantee continuous service. SQLite is not cloud replication, and an ephemeral host disk can lose data. Unattended operation requires a suitable persistent host, a durable database path, a separately managed worker process, secure private credentials, and owner review. This setup does not create accounts, obtain API keys, deploy the app, or turn it into an autonomous company.
