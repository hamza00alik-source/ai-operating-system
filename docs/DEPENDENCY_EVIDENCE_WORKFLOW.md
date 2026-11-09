# Dependency Evidence Workflow

The `.github/workflows/dependency-evidence.yml` workflow generates a time-specific inventory for the Python environment used by CI:

- CycloneDX JSON SBOM (`ci-environment.cdx.json`)
- Package license/URL/description inventory (`ci-environment-licenses.csv`)
- Exact resolved package versions (`ci-environment-freeze.txt`)

The report intentionally describes the **complete CI environment**, including application dependencies, development dependencies, and the inventory tools themselves. It is not represented as an application-only lockfile. The artifact is attached to the GitHub Actions run for 30 days and is regenerated on pull requests or by manual workflow dispatch.

## What this proves

It records the packages and license metadata visible to the inventory tools in that CI run. It provides a concrete review starting point and makes version resolution reproducible for that run.

## What this does not prove

- It is not a legal opinion or a compatibility decision.
- A package's declared license metadata may be missing, inaccurate, multi-licensed, or subject to additional notices.
- A generated SBOM does not establish that AIOS has rights to its own code or third-party copied content.
- It is not a committed lockfile and does not guarantee a future run resolves identical versions.
- It does not cover non-Python runtime components, deployment image contents, GitHub Actions themselves, or external services.
- CI inventory tools are included in the environment and must be distinguished from production dependencies during review.

## Release gate

Before commercial distribution, review the generated report, preserve all required notices, decide on license compatibility for the intended distribution model, and produce a separately reviewed application-only lock/SBOM if required. Do not market the product as fully cleared based only on a successful workflow.
