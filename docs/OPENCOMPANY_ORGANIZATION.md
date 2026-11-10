# OpenCompany Organization Charter

**Status:** Original OpenCompany design; implementation baseline for the clean-room rebuild.

## Design rule

This organization is derived from OpenCompany's own operating goals. It is not an adaptation of an imported department catalogue. Department names, mandates, role assignments, decision scopes, metrics, and approval boundaries are maintained as original OpenCompany contracts.

## Governance

The owner is the ultimate authority for strategy, budgets, identity, external commitments, publication, production deployment, credentials, payments, and other protected actions. The Executive Office coordinates work but cannot override owner approval. Department manager roles coordinate assigned specialists; they are capability assignments, not evidence that autonomous manager agents are already running.

## Departments

1. **Executive Office** — company priorities, cross-department plans, decision briefs, owner escalation.
2. **Intelligence & Research** — market evidence, competitor intelligence, source quality, opportunity assessment.
3. **Product & Innovation** — product discovery, requirements, prototypes, acceptance criteria.
4. **Engineering & AI Systems** — AI runtime, software, integrations, infrastructure, security and reliability.
5. **Media & Creative Production** — scripts, storyboards, image/video production, editing, asset provenance.
6. **Marketing & Audience Growth** — content strategy, SEO, distribution plans, organic growth measurement.
7. **Revenue & Partnerships** — marketplace research, listing drafts, pricing analysis, partnership proposals.
8. **Customer Experience & Operations** — support triage, fulfilment coordination, service knowledge and feedback.
9. **Finance & Risk** — cost controls, unit economics, financial reporting and risk escalation.
10. **Organizational Learning & Quality** — agent evaluations, independent review, incident learning and improvement proposals.

## Workforce scale and specialist teams

The initial workforce catalogue contains 250 independently authored specialist role contracts: 25 per department, arranged into five capability teams of five roles each. Above them are ten department-manager roles and one distinct Chief Executive Orchestrator role that remains subordinate to the owner. This produces 261 role contracts in total; it is a role catalogue, not a claim that 261 agents are continuously running.

Each specialist contract records a distinct title, mission, capability tags, permitted output types, prohibited actions, and deterministic team assignment. The manager is responsible for decomposing department objectives, assigning work to the relevant team, collecting handoffs, and reviewing results. The CEO/orchestrator profile can be provisioned as a draft through `POST /agents/bootstrap-executive`; specialist profiles can be provisioned through the owner-authenticated `POST /agents/bootstrap-specialists` endpoint. Provisioning is idempotent and audited; it does not activate workers or authorize external actions.

## Department contract

Each department must declare:
- One manager role key and a list of member role keys.
- A mission and explicit accountabilities.
- The decisions it may make without owner intervention.
- Measurable outcomes.
- Protected actions that remain outside its authority.

Cross-department work is represented by work items and explicit dependencies. A department name in a work item is validated against this catalogue; unknown department keys are rejected.

## Current implementation boundary

The registry and read-only API are implemented in opencompany_core.organization and GET /organization/departments. The role catalogue is exposed by GET /workforce/roles. Manager and specialist profile provisioning are owner-authenticated and create draft profiles only. This does not instantiate always-running agents. Durable specialist assignment, team-level execution, live collaboration, and worker activation remain separate implementation stages.

## Provenance

Authored from OpenCompany's stated business model and operating requirements. It does not read or import the repository's quarantined legacy data/company_departments.json or Agency-Agent materials.
