# OpenCompany test boundaries

## Default discovery

The default pytest configuration retains normal test discovery and excludes
only the 11 historical test files that directly import the quarantined `ai_os`
package. Other tests, including the wider `opencompany_*` unit and integration
tests, remain part of default discovery.

The excluded legacy files are:

- `tests/test_agent_runtime.py`
- `tests/test_api.py`
- `tests/test_brain.py`
- `tests/test_business_ops.py`
- `tests/test_credentials.py`
- `tests/test_owner_session_auth.py`
- `tests/test_provider_failover.py`
- `tests/test_research_sources.py`
- `tests/test_sessions_and_workforce.py`
- `tests/test_website_api.py`
- `tests/test_workflows.py`

## Legacy suite

Historical tests that import `ai_os` remain in their existing locations for
reference and controlled maintenance. They are not part of default discovery.
Do not treat their presence as evidence that the legacy runtime is part of
OpenCompany's supported runtime.

Legacy tests may be invoked individually by overriding the default ignore list,
for example: `pytest -o addopts='' tests/test_api.py`. Use this only when a
maintainer is deliberately working on the legacy runtime. Do not combine
them with the OpenCompany suite or use them as acceptance evidence for
OpenCompany.

## Testing deferral

Per owner instruction, do not run tests or CI before 2026-12-01. This document
and the pytest discovery boundary are configuration changes only; no test
execution or result is claimed.

After the deferral, run the OpenCompany suite independently first, then
decide whether legacy tests need a separate maintenance workflow or should be
retired. Any CI workflow changes must also account for the active
`feature/opencompany-aios-unification` branch and the actual PR base branch;
do not change production workflows or deploy as part of test isolation.
