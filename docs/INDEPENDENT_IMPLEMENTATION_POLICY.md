# Independent Implementation and Clean-Room Policy

**Status:** Mandatory engineering policy  
**Applies to:** All new and replacement OpenCompany AI Operating System components  
**Objective:** Build independently authored software and reduce third-party copyright and licence exposure.

## 1. Non-use rule

OpenCompany will not copy, import, vendor, fork, adapt, translate, mechanically transform, or reuse source code, prompts, agent definitions, templates, documentation text, tests, distinctive UI assets, or other expressive materials from Agency-Agent or any reference repository.

Reference repositories are not implementation dependencies. They must not be installed, executed, vendored, or used as source material for implementation.

## 2. Permitted requirements research

Where appropriate, public references may be used only to identify general product needs or publicly observable capabilities. Engineers must record requirements in neutral, implementation-independent language. Do not reproduce distinctive wording, architecture diagrams, naming systems, schemas, code organization, prompt text, or other expressive choices from a reference.

A rewrite performed after studying source code is not automatically independent and does not guarantee freedom from copyright claims. When meaningful source-code exposure has occurred, use a clean-room separation: one reviewer may document high-level functional requirements without passing source expression or implementation details to the independent implementer. For the strongest separation, the implementer must not inspect the reference source.

## 3. Independent design and authorship

Every replacement component must have:
- A new design derived from OpenCompany's own product requirements.
- Independently chosen names, interfaces, data structures, control flow, and tests.
- A dated design record and implementation record.
- Original tests written from behavioural requirements, not copied from reference tests.
- A provenance record identifying authors, tools, dependencies, and any external material consulted.

Do not preserve a reference implementation's distinctive structure merely by renaming variables or changing syntax.

## 4. Existing OpenCompany code

Existing repository code is not presumed original merely because it is in this repository. Each component must be reviewed for provenance before it is retained in a release.

Components with uncertain or third-party-derived provenance must be isolated from the clean implementation until independently replaced or cleared by documented licence review. Preserve history; do not erase or rewrite Git history to conceal origins.

## 5. Third-party dependencies

Ordinary libraries may be used only after recording the exact package, version, licence, source, and purpose in a software bill of materials. Dependencies must be selected for their own documented functionality, not copied from reference repositories as a bundle. Review transitive dependencies and commercial-use restrictions.

## 6. Verification gates

A component is not marked independently implemented until:
1. Its requirements are documented without copied expression.
2. Its design and implementation provenance are recorded.
3. Static checks and relevant tests pass.
4. Its dependencies and licences are reviewed.
5. A similarity/provenance review finds no unexplained overlap with restricted source material.
6. Security, privacy, cost, and human-approval controls are verified.

No audit can guarantee that a copyright claim will never arise. Obtain qualified legal advice before public or commercial distribution.

## 7. Operational safety

This policy does not authorize spending, paid API usage, publishing, customer contact, financial transactions, production database changes, credential rotation, or production deployment. Those actions remain subject to the owner's separate approval.

## 8. Current known contamination risks

The existing repository README describes a 283-role specialist catalogue sourced from `hamza00alik-source/agency-agents`, stores it in `data/agency_agents_manifest.json`, and describes runtime retrieval of specialist instruction files from that repository. Under this policy, that catalogue and runtime retrieval must not be used by the clean-room implementation. They must be quarantined and replaced with independently authored OpenCompany role specifications.

The repository also contains a source inventory of reference projects. That inventory may be retained only as an audit/provenance record; it must not drive code generation, runtime loading, dependency installation, or implementation copying.
