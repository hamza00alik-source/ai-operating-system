# AI Code Asset Management Department

**Status:** Planned, owner-supervised department. This document defines its operating contract; it does not claim that repository scanning, tokenization, licensing, or revenue collection is already live.

## Mission

Turn company-owned software and code artifacts into documented, defensible, licensable assets while protecting the company from accidental disclosure, third-party rights violations, misleading ownership claims, and unauthorized commercial commitments.

## Department roles

- **IP Asset Manager:** owns the inventory, workflow, risk queue, and department reporting.
- **Repository Auditor:** records repository identity, visibility, default branch, commit history, file inventory, provenance, and technical condition.
- **License Compliance Analyst:** inventories dependency manifests and license files; flags incompatible, missing, unknown, or restrictive terms. It does not give legal opinions.
- **Tokenomics Analyst:** reports source-code and Git-history token volumes with explicit tokenizer, model/tokenizer version, included paths, exclusions, and measurement date.
- **Licensing Research Analyst:** researches buyer eligibility, platform rules, supported jurisdictions, payout methods, fees, and evidence requirements from primary sources.
- **Licensing Package Specialist:** prepares private, owner-reviewable technical and commercial documentation.
- **Licensing Revenue Analyst:** records offers, status, term, royalty/recurring terms, invoices and receipts supplied or verified by the owner.

## Asset record

Each asset should have:
- Stable internal asset ID and canonical repository URL.
- Repository owner/account, visibility, default branch, snapshot commit SHA, scan timestamp.
- Provenance classification: `company-created`, `contributor-created`, `third-party`, `mixed`, or `unknown`.
- Ownership evidence references and contributor/assignment status.
- Dependency inventory: package, version, ecosystem, declared license, source URL, direct/transitive status, and evidence timestamp.
- License evidence: repository license file, SPDX identifier if detected, notices, and unresolved questions.
- Technical profile: languages, file counts, source bytes, generated/vendor/binary exclusions, tests, CI, documentation, and security findings.
- Token metrics: source-only and history-only counts, method, tokenizer identity/version, commit range, inclusion rules, and confidence.
- Readiness: `blocked`, `needs-evidence`, `review-required`, `package-ready`, or `owner-approved`.
- Commercial fields: candidate license models, buyer/platform research, offer records, term, recurring terms, currency, gross/net amount, status, and evidence source.

## Token-volume measurement policy

Never label a character/4 estimate as an exact token count. Prefer the actual tokenizer for a named target model when available. Store source-code and Git-history metrics separately; report whether history means all reachable commits or a bounded commit range. Exclude generated files, vendored dependencies, binaries, lockfiles, and secrets from the company's own-code metric, but retain dependency metadata separately. Record exclusions and tokenizer version so results are reproducible. If the exact tokenizer is unavailable, return a clearly labelled estimate and confidence level rather than inventing precision.

## Licensing readiness gates

A repository is not license-ready merely because it is public or appears in the company's GitHub account. The department must verify:
1. The company has documented rights to every material component it proposes to license.
2. Contributor ownership/assignment and employer/contractor obligations are understood.
3. Third-party dependencies and their licenses permit the proposed distribution and sublicensing model.
4. Notices, attribution, source-disclosure, patent, trademark, and copyleft obligations are identified.
5. Secrets, personal data, customer data, and confidential material are excluded.
6. Buyer/platform eligibility, geography, KYC, payment rails, payout thresholds, fees, taxes, and refund/dispute terms are researched from current primary sources.
7. A human/legal review is obtained where rights or terms are ambiguous.

Any unknown ownership or material dependency license blocks a `package-ready` decision.

## Owner approval boundary (hard control)

The department may perform internal read-only audits and prepare private drafts. It must not, without explicit owner approval for the specific action:
- Share or expose a repository, source file, archive, or private link with a prospective buyer or third party.
- Mint/create a token, NFT, certificate, or other on-chain/off-chain ownership instrument.
- Submit a repository, listing, proposal, offer, or application to an external marketplace, buyer, registry, or platform.
- Sign, accept, negotiate binding terms, issue a legal representation, or create/execute a contract.
- Grant, transfer, sell, sublicense, or otherwise license any asset.
- Collect, move, refund, or otherwise transact money.

Approval must be tied to the exact asset, recipient/platform, material to be shared, commercial terms, and action. A general approval is not a standing authorization. Rejected, expired, or missing approval means the action remains blocked.

## Commercial pipeline

`discovered -> inventoried -> rights-review -> dependency-review -> technical-review -> buyer-research -> package-draft -> owner-review -> owner-approved -> externally-submitted -> offer-received -> agreement-review -> licensed -> revenue-verified`

The system may record later states only when evidence exists. It must never infer that an offer, contract, license, or payment happened from a draft or external page view.

## Initial implementation sequence

1. Add department registry and this operating contract.
2. Add persistent asset, provenance, dependency, token-metric, buyer-research, offer, and approval records.
3. Implement read-only repository snapshot scanning and auditable token metrics.
4. Add owner dashboard inventory, risk flags, and approval queue.
5. Add private licensing-package generation and offer/revenue ledger.
6. Add external marketplace integrations only after platform-specific research and explicit owner approval.

## Non-goals

This department is not a code resale bot, token/NFT minting service, automated legal advisor, or automatic marketplace publisher. It does not claim ownership based on repository visibility, commit authorship alone, or a GitHub account association.