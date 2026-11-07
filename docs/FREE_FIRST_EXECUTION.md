# Free-first execution model

The operating system must not depend on paid model APIs to be useful.

## What is free and available now

- The Agency Agents source repository provides reusable agent role profiles and workflow instructions under its MIT license.
- This repository contains an initial role catalog and a provider-neutral registry.
- `GET /runtime` reports which execution modes are enabled.
- `POST /work-packets` creates a ready-to-paste specialist prompt without contacting any model provider.
- The generated prompt includes evidence standards, safety boundaries, and an output format.

## Manual free-chat workflow

1. Create a work packet for an enabled agent using the API docs at `/docs`.
2. Copy the returned `prompt_text`.
3. Paste it into a free AI chat interface that you already have access to.
4. Review the result and evidence; do not assume the chat interface has accessed external tools unless it shows that it has.
5. Bring the result back into the operating system for review and follow-up.

This mode does not call an API, incur API usage charges, or run autonomously. It does require a person to transfer the prompt and result between interfaces.

## Future free/local model support

A local model runtime (for example, Ollama on hardware that can run it) can be added behind a provider interface. It must be optional, report hardware requirements clearly, and never silently fall back to a paid provider. A local runtime is not automatically feasible on an Android-only device; a separate computer or suitable hosted machine may be needed.

## Hard cost controls

- No provider API is configured by default.
- Paid API calls remain disabled.
- No automatic paid fallback.
- No subscriptions, purchases, cloud deployments, or metered services without explicit owner approval.
- Before enabling any provider, display whether it is free, limited, metered, or paid and require explicit approval.

## Current limitations

Agent work packets are prompt preparation, not AI execution. The system cannot independently reason or continue working while the owner is offline in this mode. Autonomous operation requires an available model runtime plus a persistent worker, secure tool permissions, durable state, and authenticated approval gates.
