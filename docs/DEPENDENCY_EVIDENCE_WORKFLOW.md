# Dependency Evidence Workflow

The `.github/workflows/dependency-evidence.yml` workflow generates two deliberately separate Python dependency views:

## Complete CI environment

- CycloneDX JSON SBOM (`ci-environment.cdx.json`)
- Package license/URL/description inventory (`ci-environment-licenses.csv`)
- Exact resolved package versions (`ci-environment-freeze.txt`)

This includes application dependencies, development dependencies, and inventory tooling. It is useful for understanding the CI runner, but it is not the production dependency list.

## Application runtime dependencies

- `application-requirements.lock.txt`: a time-specific, pinned resolution of the runtime dependencies declared in `pyproject.toml`, including transitive Python packages.
- `application-runtime.cdx.json`: CycloneDX inventory generated from that application-only lock.

The application-only lock is generated during CI with pip-tools. It is attached to the run artifact rather than committed as a permanent lockfile. Re-run the workflow to refresh the resolution. It does not lock the Python interpreter, operating system, deployment image, GitHub Actions, or external services.

## What this proves

It records package versions and license metadata visible to the inventory tools in that CI run. The separate application-runtime files help reviewers distinguish production Python dependencies from development and evidence tooling.

## What this does not prove

- It is not a legal opinion or a compatibility decision.
- Package license metadata may be missing, inaccurate, multi-licensed, or subject to additional notices.
- An SBOM does not establish that AIOS owns its source code or has rights to third-party copied content.
- The lock is a time-specific CI artifact, not a committed release lock and not a guarantee that a future run resolves identically.
- It does not cover non-Python runtime components, deployment image contents, GitHub Actions themselves, or external services.

## Release gate

Before commercial distribution, review the application-only lock and SBOM, verify package licenses and required notices against the intended distribution model, and preserve applicable notices. Do not market the product as fully cleared based only on a successful workflow.
