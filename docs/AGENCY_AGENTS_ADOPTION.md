# Agency Agents as the Primary Agent Foundation

## Decision

Use `hamza00alik-source/agency-agents` (upstream: `msitarzewski/agency-agents`) as the primary source for specialist role definitions, agent responsibilities, workflows, deliverables, and team/runbook composition.

The AI Operating System remains the execution platform we own. The Agency Agents repository is an agent-role corpus and design reference; it is not, by itself, a complete autonomous runtime or company operating system.

## What we verified

- The repository contains specialist Markdown agent profiles with frontmatter and detailed instructions.
- Profiles describe identity, mission, responsibilities, workflows, safety rules, tools, and expected deliverables.
- `strategy/runbooks.json` defines scenario team rosters and activation groups.
- The repository includes installer/conversion scripts for external coding-agent tools.
- Its LICENSE file states MIT. Any copied/adapted substantial portions must retain the required copyright and license notice.
- The upstream README describes integrations with multiple coding tools. We will not adopt Claude, Grok, or Kimi as model providers or required components.

## How it will be used

1. **Agent catalog:** adapt selected profiles into a versioned, machine-readable catalog while retaining source attribution.
2. **Agent runtime:** build our own provider-neutral runtime to load profiles, construct bounded task context, call configured model adapters, validate outputs, and record results.
3. **Orchestration:** use runbook concepts to compose teams, but execute work through our own task engine, dependencies, retries, and audit trail.
4. **Memory:** store durable company knowledge separately from agent personas; cite sources and keep tenant/company data isolated.
5. **Approvals:** require explicit human approval before publishing, spending, purchases, external customer messages/commitments, or production changes.
6. **Evaluation:** test agent outputs against task-specific acceptance criteria; do not treat role prompts or self-reported success as proof.
7. **Reference projects:** inspect the other selected repositories for useful orchestration, memory, scheduling, deployment, observability, security, and integration patterns. Reuse only after checking license, maintenance, security, dependencies, and fit.

## Initial departments

- Executive/orchestration and project management
- Research and product
- Engineering and AI
- Design and quality assurance
- Marketing and content
- Sales operations (no unsolicited cold outreach)
- Customer support
- Finance and compliance analysis (no autonomous money movement)

## Non-negotiable operating boundaries

- No automatic spending, purchases, publishing, or customer commitments.
- No credentials, customer records, or private company data in the public agent catalog.
- No autonomous production code modification.
- Agents must not invent tool access or claim actions they did not execute.
- All external actions require permission checks at the execution layer, not merely prompt instructions.

## Build sequence

1. Agent profile schema, loader, registry, and source attribution.
2. Provider-neutral model adapter interface.
3. Task planner, orchestrator, agent handoff, and execution records.
4. Human approval service and audit events.
5. Persistent memory and retrieval with source citations.
6. Evaluation harness, retries, observability, and background scheduling.
7. Dashboard and business integrations after authentication and authorization are in place.

## Reference repositories

The following are research references, not dependencies to merge wholesale:

1. `saurav-yirifi/blueprint-ai-first-company`
2. `itsPremkumar/ai-company`
3. `RagaviDevX/ai-company-agent-platform`
4. `bdno1agency/ai-tech-team-company-live`
5. `psorii/one-person-ai-company-starter`
6. `paulswarna794-boop/ai-automation-company-setup`
7. `qaptanjes/claude-code-ai-company` (reference only; do not adopt Claude)
8. `StellarRequiem/verified-ai-labor`
9. `complianceguardaireports-wq/MavadoClaw-Worker001`
10. `bmacbuilds/bmac.one`

Each candidate component must be reviewed independently for provenance, license compatibility, security, operational cost, and testability before adoption.
