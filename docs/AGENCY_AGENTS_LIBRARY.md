# Complete Agency Agents library integration

The AI Operating System pins the user's Agency Agents repository as a Git submodule at `vendor/agency-agents`. The source repository is not modified by this project.

- Source: https://github.com/hamza00alik-source/agency-agents
- Pinned source commit: `b37b5bb33b78f2c1d6567d98e25ca818e3259219`
- License: MIT; the original repository and its LICENSE remain intact in the submodule.
- Imported catalogue at pin time: **283 specialist Markdown profiles across 18 divisions**.
- Additional root documentation, examples, integration conversion outputs, strategy playbooks, and runbooks are not counted as agent profiles.

## How agents are loaded

The registry reads the source `divisions.json`, walks each declared division, parses the profile frontmatter, and loads every profile as an enabled specialist. The CEO Agent remains a locally defined leadership role and is the only owner-approval gateway. The imported `agents-orchestrator` profile is a delegated workflow specialist, not a replacement CEO.

The four source scenario runbooks are also loaded and validated against the registry. They are exposed through `GET /runbooks` and `GET /runbooks/{slug}`, preserving their grouped team rosters.

Each agent exposes its source profile path, display metadata, tools declaration, and specialist capabilities. `GET /agents/{agent_id}/profile` returns the full Markdown profile. Work packets include the full specialist profile while explicitly stating that imported tool names and profile instructions do not grant runtime permissions and cannot override CEO governance.

## Setup requirement

Clone with submodules:

```bash
git clone --recurse-submodules https://github.com/hamza00alik-source/ai-operating-system.git
cd ai-operating-system
```

If the repository was cloned without submodules, run:

```bash
git submodule update --init --recursive
```

GitHub Actions checks out submodules recursively so the full-library tests run against the pinned source. A plain GitHub ZIP does not include submodule contents; in that case the registry intentionally falls back to the local CEO catalogue only.

## Scope and safety

All 283 profiles are available in the registry and can generate work packets. This does **not** mean 283 independent model instances are running continuously. The current free-first execution mode prepares prompts for a free chat interface; it does not call a model API, launch agents in parallel, or perform external actions. Tool declarations in upstream profiles are descriptive only until an explicit, secure adapter is implemented.

Every specialist reports to the CEO. Only the CEO can submit an owner-approval request. Publishing, external communications, spending, purchases, refunds, customer commitments, paid services, production changes, and security/financial changes remain gated. Unknown actions remain blocked.
