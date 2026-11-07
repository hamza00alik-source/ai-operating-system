# Agent Zero Compatibility Evaluation

**Status:** Proposed evaluation; no installation or external service enabled  
**Owner:** OpenCompany AI CEO  
**Constraint:** Zero spend. No paid API, subscription, hosting, purchase, publication, or production credential changes.

## Executive decision

Agent Zero is a candidate execution environment, not a replacement for the OpenCompany AI Operating System and not a model provider. Evaluate it only as an optional worker/runtime after the existing operating system has the minimum orchestration and security foundations.

## Verified current baseline

The AI Operating System README describes an early FastAPI/SQLite starter with task and approval records, health checks, and API-key protection for non-development deployments. It explicitly says external AI providers, background workers, ecommerce, and social integrations are not connected.

The roadmap still lists the agent registry, task assignment/dependencies, retries/timeouts/logs, background worker/scheduler, provider-neutral LLM adapter, integrations, and operational dashboard as incomplete.

The deployment guide documents a prospective Enzonic free hosting profile of 512 MB RAM, 1 CPU core, and 1 GB storage, subject to availability and provider terms. It explicitly says this is suitable only for the lightweight API and small jobs, not large language models or multiple heavy agent processes. It also says deployment has not been confirmed.

## Agent Zero findings

- Agent Zero is an open-source agent framework with a Linux workspace, tools, browser/terminal capabilities, and persistent user workspace.
- Its official installation guide requires a supported AI account, provider API key, or local model server to chat; the framework does not include unlimited free inference.
- The documented supported deployment path is Docker-based, using a desktop launcher or server/shell installer. It is not an Android-phone-only hosting solution.
- It supports configurable main and utility models and can use local model servers, but the chosen host must have adequate compute and persistent storage.

## NVIDIA NIM / API Catalog restrictions

NVIDIA's current NIM FAQ says Developer Program access to hosted NIM API endpoints and downloadable microservices is for prototyping, research, development, and testing. It is not licensed for production use or real end-user business transactions. NVIDIA says production use requires an NVIDIA AI Enterprise license. Per-model request limits vary and must be checked in the NVIDIA account/catalog.

Therefore, NVIDIA free developer access may be used only for an isolated technical evaluation. Do not route OpenCompany customer work, live fulfillment, or production requests through it on the assumption that it is a free commercial tier.

## Compatibility gate

Do not install or integrate Agent Zero until all of the following are true:

1. A suitable existing computer/server is confirmed, with Docker support and persistent storage, at zero additional cost.
2. The existing AI OS has a provider-neutral model adapter and a controlled agent/task interface.
3. Agent Zero can be invoked through a documented, authenticated interface without exposing its host tools or secrets to untrusted tasks.
4. Tasks, logs, outputs, and approvals can be correlated with the AI OS records.
5. The owner approval boundary remains enforced for publishing, customer communications, purchases, spending, and production changes.
6. The integration can be disabled or removed without losing AI OS data.

## Test plan (offline/mock first)

- Review Agent Zero API/integration surface and authentication model.
- Build a small mocked adapter proof-of-concept in a separate branch or isolated test environment.
- Send one harmless task from the AI OS to the Agent Zero test worker.
- Verify task ID correlation, status reporting, output capture, timeout, failure handling, and retry behavior.
- Verify that the worker cannot bypass approval gates or access store/payment credentials.
- Measure memory, CPU, response time, and persistence behavior on the intended free host.
- If a free NVIDIA key is available, use it only for a bounded development/test request after reviewing the displayed limits and terms. Do not place keys in GitHub or logs.

## Pass / fail criteria

**Pass:** A zero-cost, persistent, authenticated, reversible test demonstrates reliable task dispatch and result return while preserving approval gates and fitting the actual host limits.

**Fail / defer:** Requires paid hosting/API, an unsupported phone-only deployment, weak isolation, production use of trial-only NVIDIA endpoints, or a worker that bypasses approval controls.

## Recommended implementation order

1. Finish the AI OS audit and confirm actual deployment/hosting facts.
2. Implement the minimal provider-neutral model adapter and agent registry.
3. Implement task execution logs, timeouts, retries, and approval enforcement.
4. Run a mock worker integration test.
5. Only then decide whether Agent Zero adds enough value to justify integration.

## Current decision

**DEFER INSTALLATION.** Continue architecture and compatibility work without spending money, adding hosting, connecting production credentials, or changing live store operations.