# Local Model Behavior Regression Tests

## Purpose

The static instruction screen checks candidate text for a narrow set of unsafe patterns. This optional second stage compares the current active instruction baseline with the same specialist prompt plus an unactivated candidate addendum. It runs fixed regression fixtures through a local OpenAI-compatible inference endpoint.

It does not automatically activate a candidate. It records baseline and candidate report hashes, rubric scores, fixture checks, the active instruction version used for comparison, model identifier, and timestamp. Raw model reports are not persisted.

## Strict local-only gate

All of the following must be true before the endpoint makes a model request:

- AI_OS_BEHAVIOR_TEST_ENABLED=true
- AI_OS_MODEL_ENABLED=true
- AI_OS_MODEL_BACKEND=openai_compatible
- AI_OS_MODEL_BASE_URL points to localhost, 127.0.0.1, or ::1 using HTTP or HTTPS
- AI_OS_MODEL_NAME is configured
- AI_OS_MODEL_API_KEY is unset

The CLI backend, remote endpoints, and API keys are rejected. The app passes no tools schema and makes two completion calls per fixture: one baseline and one candidate. An explicit owner token is required for the test endpoint.

Example opt-in configuration for a locally running compatible inference server:

```bash
export AI_OS_BEHAVIOR_TEST_ENABLED=true
export AI_OS_MODEL_ENABLED=true
export AI_OS_MODEL_BACKEND=openai_compatible
export AI_OS_MODEL_BASE_URL=http://127.0.0.1:8000/v1
export AI_OS_MODEL_NAME=your-local-model
unset AI_OS_MODEL_API_KEY
```

No local inference server is bundled or started by this project. The model host must be controlled and restricted by the operator; this application does not sandbox the inference server process itself. A local server may still have host-level network or tool permissions outside this application's control.

## Fixtures and interpretation

- source-grounded-research: asks the specialist to use synthetic supplied source material and include its exact URL in evidence.
- missing-evidence-blocker: asks the specialist to block rather than invent evidence when no source material is supplied.

The candidate passes only when its deterministic report rubric and fixture-specific checks pass, and its score is no lower than the baseline. Signals distinguish provisional_improvement from no_regression_only. A no-regression result is not evidence of a quality improvement.

If a behavior test has been run for a proposal, activation requires the latest result to pass for the exact current candidate text and the same active baseline version. A later change to the active baseline invalidates the old comparison and requires a rerun. If no behavior test has been run, the existing static screen plus separate owner-token activation path remains available for zero-cost setups without a local model server.

## API

- GET /behavior-tests/status reports whether the local-only test backend is ready and lists fixtures.
- POST /improvement-proposals/{proposal_id}/behavior-test?fixture_id=source-grounded-research runs the paired comparison. Requires the owner token and local opt-in.
- GET /improvement-proposals/{proposal_id}/behavior-tests returns persisted results.

All test runs are audit-logged. They never activate or mutate instructions. See INSTRUCTION_VERSIONING.md for the full adoption and rollback lifecycle.
