# Approved Action Gateway

## Scope

ai_os.action_gateway is an internal server-side execution boundary. It is not exposed as an HTTP endpoint and no production adapters are registered by default.

The gateway:
1. accepts an approval ID, action type, exact parameters, and unique execution ID from trusted server code;
2. refuses to proceed when AI_OS_EXTERNAL_ACTIONS_ENABLED is not exactly true;
3. checks that a trusted application adapter is registered for the action before consuming the approval;
4. atomically consumes the one-time owner approval only when action type and every parameter match the approved hash;
5. invokes the registered adapter and records started/completed/failed audit events;
6. records only a hash of the adapter result in the audit trail.

## Adapter contract

Adapters are registered during trusted application initialization through register_action_adapter. There is no API to register an adapter from a request, agent prompt, or dashboard. An adapter receives the approved parameter object and unique execution ID. It must implement its own idempotency using that execution ID.

The approval is consumed before the adapter is called. If an adapter fails, the approval remains consumed and the gateway records a failure event. It does not automatically retry because a blind retry could duplicate a real-world side effect. Operators must inspect the adapter state and audit trail before any manual recovery.

## Current safety state

- AI_OS_EXTERNAL_ACTIONS_ENABLED defaults to false.
- No WooCommerce, social-platform, messaging, payment, refund, purchase, or deployment adapter is registered.
- The dashboard can record an owner decision, but it cannot execute the action.
- The gateway has no public execution route.
- The tests use a test adapter and do not contact external services.

Do not enable the external-action flag or connect production credentials until each adapter has its own least-privilege credentials, idempotency, timeout handling, request/response validation, reconciliation, audit coverage, and integration tests. The owner approval hash is necessary but not sufficient for safe external execution.