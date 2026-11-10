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

## Department contract

Each department must declare:
- One manager role key and a list of member role keys.
- A mission and explicit accountabilities.
- The decisions it may make without owner intervention.
- Measurable outcomes.
- Protected actions that remain outside its authority.

Cross-department work is represented by work items and explicit dependencies. A department name in a work item is validated against this catalogue; unknown department keys are rejected.

## Current implementation boundary

The registry and read-only API are implemented in opencompany_core.organization and GET /organization/departments. This does not instantiate ten always-running manager agents. Agent provisioning, durable assignments, dashboard controls, and live collaboration are separate implementation stages.

## Provenance

Authored from OpenCompany's stated business model and operating requirements. It does not read or import the repository's quarantined legacy data/company_departments.json or Agency-Agent materials.
