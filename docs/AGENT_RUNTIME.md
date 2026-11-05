# Agent registry and planning API

The first runtime milestone is deliberately deterministic and provider-neutral.

## Current capabilities

- Loads enabled role definitions from `agents/catalog.json`.
- Exposes role discovery at `GET /agents`.
- Creates a non-executing work plan at `POST /plans`.
- Routes only by exact department name; unknown departments return 404.
- Marks plans as `execution_enabled: false` until a model adapter, durable job runner, tool permission layer, and authenticated approval workflow are implemented.

## Example

```bash
curl http://localhost:8000/agents
curl -X POST http://localhost:8000/plans \
  -H "Content-Type: application/json" \
  -d '{"title":"Research customer demand","description":"Find evidence","department":"research"}'
```

## Department IDs

`leadership`, `research`, `product`, `engineering`, `marketing`, `content`, `support`, `analytics`.

## Safety boundary

This registry is not a permission system. A profile's approval metadata is descriptive until enforced by authenticated server-side policy. No agent currently calls an LLM, executes code, accesses customer data, sends messages, publishes content, spends money, or changes production. Keep those actions disabled until authorization, audit logging, secret management, idempotency, and human approval are implemented and tested.

## Source and attribution

The role taxonomy and specialist workflow concepts are informed by [Agency Agents](https://github.com/msitarzewski/agency-agents), which is MIT-licensed. This repository's catalog metadata, registry, planning API, and execution controls are independent implementations. Any future copied or adapted upstream files must retain the applicable MIT copyright and license notice.
