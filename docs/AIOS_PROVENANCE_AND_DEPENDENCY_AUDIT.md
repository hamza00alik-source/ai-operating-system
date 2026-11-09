# AIOS Provenance and Dependency Audit — Follow-up

**Assessment type:** Read-only source-lineage and dependency-declaration review  
**Snapshot:** PR branch `feature/code-asset-management-department`, commit after this report is added  
**Purpose:** Correct the workforce-catalogue lineage and make runtime source retrieval reproducible  
**Status:** Partial evidence recorded; commercial licensing remains blocked

## 1. Workforce catalogue lineage — verified

AIOS references an account-owned repository named `hamza00alik-source/agency-agents`. GitHub metadata identifies this repository as a **fork** whose parent and source are `msitarzewski/agency-agents`. The account-owned fork's repository metadata reports `license: null`, even though its `LICENSE` file contains MIT text. The upstream parent repository is not marked as a fork, GitHub identifies its license as MIT, and the pinned upstream revision contains the same MIT license text.

Verified upstream revision used by this AIOS manifest:

- Canonical upstream: https://github.com/msitarzewski/agency-agents
- Pinned commit: `b37b5bb33b78f2c1d6567d98e25ca818e3259219`
- Commit URL: https://github.com/msitarzewski/agency-agents/commit/b37b5bb33b78f2c1d6567d98e25ca818e3259219
- Upstream LICENSE at that commit: https://github.com/msitarzewski/agency-agents/blob/b37b5bb33b78f2c1d6567d98e25ca818e3259219/LICENSE
- Account-owned fork: https://github.com/hamza00alik-source/agency-agents
- Fork head observed during audit: `b37b5bb33b78f2c1d6567d98e25ca818e3259219`
- Upstream HEAD observed during audit: `8ae6164602c95ca78828b148b9052460ee426885`

The pinned commit exists in the upstream repository. AIOS now identifies the canonical upstream and that exact commit in `data/agency_agents_manifest.json`. Every specialist source URL is a commit permalink. The agent runtime now fetches role Markdown from the raw-content URL for that exact repository and commit, rather than following the mutable `main` branch. Runtime validation rejects an unpinned revision, a different repository, or unsafe paths. This improves reproducibility; it does not certify the authorship of upstream materials or prove that every upstream contributor had authority to license every contribution.

The MIT notice identifies **AgentLand Contributors** as copyright holder. AIOS must preserve that notice and attribution when redistributing substantial portions of the upstream catalogue. The manifest's MIT label is a source-license reference, not a claim that AIOS owns the catalogue.

## 2. How the catalogue is used

- `data/agency_agents_manifest.json` stores role names, departments, paths, and source links; it does not contain the full specialist Markdown instructions.
- The runtime fetches one selected role's Markdown on demand as untrusted prompt context.
- The fetched Markdown is not executed as code and does not give the role independent tools or a separate always-on process.
- The workforce catalogue is third-party content under the upstream MIT notice, not original AIOS code.
- The account-owned fork is a mirror/reference point only; AIOS now retrieves from the canonical upstream at the pinned revision.

## 3. Other repository references

`data/repository_sources.json` lists additional repositories as `reference-only`. The declared policy says these are architecture/documentation references, not installed dependencies or code that AIOS executes. This audit did not perform a complete line-by-line similarity/provenance comparison against all reference repositories. Therefore, “reference-only” is a project declaration, not an independently proven absence of copied/adapted snippets. Before commercial distribution, retain source notes for any implementation pattern materially adapted from those projects and review its applicable license.

## 4. Python dependency declaration

The project declares these direct runtime dependencies in `pyproject.toml` and repeats the same direct set in `requirements.txt`:

| Package | Declared range | Role |
|---|---:|---|
| fastapi | `>=0.110,<1.0` | HTTP API framework |
| uvicorn[standard] | `>=0.27,<1.0` | ASGI server |
| pydantic | `>=2.6,<3.0` | Data validation |
| cryptography | `>=42,<47` | Credential encryption |
| pytest | `>=8.0,<9.0` | Development/test extra |
| httpx | `>=0.27,<1.0` | Development/test extra |

No dependency lockfile was present in the reviewed PR-branch tree. These are version ranges, not an exact resolved dependency inventory. The GitHub Actions CI install proves the test environment could resolve and install a compatible set at that run; it does not preserve a complete versioned SBOM or prove every transitive package's license. No claim is made here that all direct/transitive licenses, notices, vulnerability status, or redistribution obligations have been cleared.

## 5. Required next evidence

1. Generate a reproducible, version-pinned dependency lock and an SPDX or CycloneDX SBOM from a controlled build environment.
2. Review direct and transitive dependency licenses and preserve required notices.
3. Compare AIOS source files and commit history against declared reference repositories to identify copied/adapted material.
4. Establish contributor/contractor rights for AIOS-authored code.
5. Run a secret scan on repository history and deployment configuration; this audit does not certify secrets are absent.
6. Obtain qualified legal review for any uncertain ownership, contribution, or redistribution issue.

## 6. Commercial decision

**Still blocked / not approved for sale, licensing, sublicensing, exclusivity claims, or source-code distribution.** The upstream MIT catalogue can be used subject to its terms, but that permission does not grant ownership of the catalogue or resolve rights in AIOS's own code, other third-party materials, dependencies, or contributor work.

No buyer listing, external package sharing, license grant, contract, purchase, or financial action was performed.
