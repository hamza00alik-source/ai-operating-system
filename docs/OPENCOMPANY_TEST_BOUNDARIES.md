# OpenCompany test boundaries

## Default discovery

The default pytest configuration discovers only `test_opencompany_*.py` files.
This keeps the independent OpenCompany suite separate from the historical
`ai_os` test suite while the legacy runtime remains quarantined.

The current independent suite is:

- `tests/test_opencompany_app.py`

## Legacy suite

Historical tests that import `ai_os` remain in their existing locations for
reference and controlled maintenance. They are not part of default discovery.
Do not treat their presence as evidence that the legacy runtime is part of
OpenCompany's supported runtime.

Legacy tests may be invoked individually by explicitly passing their file
paths to pytest when a maintainer is working on the legacy code. Do not combine
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
