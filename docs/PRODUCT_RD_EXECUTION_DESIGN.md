# Product & R&D execution design

## Objective

Make Product & R&D an executable department in the current OpenCompany runtime. The department owns internal product discovery, specifications, production, artifact creation, QA, packaging, and listing-draft preparation. The CEO coordinates and reviews evidence. The owner retains authority over external publication, spending, customer commitments, and account changes.

This design is for the current standalone implementation in `src/opencompany_app` and `src/opencompany_core`. It must not extend the quarantined `src/ai_os` runtime or copy the older Product & R&D prototype without adapting it to current architecture.

## Existing platform capabilities to reuse

- Canonical department and role contracts in `opencompany_core.organization` and `opencompany_core.workforce`.
- Business-scoped, immutable work items and same-business dependency validation.
- CEO planning, manager delegation proposals, owner approval, durable queue admission, worker execution, review-required deliverables, handoffs, and audit events.
- Commercial product catalogue in `ProductPersistenceMixin`.
- Owner-authenticated API routes and the mobile-friendly OpenCompany dashboard.
- Strict zero-cost model gateway. A missing or unverified free provider must fail closed.

The Product & Innovation department is the current canonical department key: `product-innovation`. Product work for the user's downloadable-product business must use `business_id=digital-products`. Product workflows must never silently default to `core` or mix records with the physical-products agency or own physical-products brand.

## Required workflow

The product record moves through these ordered stages:

1. `opportunity_brief` — evidence, target buyer, job-to-be-done, alternatives, demand confidence, and unresolved assumptions.
2. `product_specification` — user, use case, deliverables, formats, compatibility targets, requirements, acceptance criteria, and exclusions.
3. `production_plan` — work breakdown, assigned Product & Innovation roles, deterministic generation steps, dependencies, and estimated zero-dollar cost.
4. `artifact_generation` — create original files from the approved specification; record exact artifact IDs, hashes, sizes, and provenance.
5. `automated_qa` — run reproducible file, format, structure, archive, manifest, checksum, and policy checks. Failure blocks downstream stages.
6. `human_preview` — create a preview/contact sheet or other review surface. This is a required human visual-review checkpoint; never mark visual quality as passed by inference.
7. `packaging` — create a reproducible customer package with usage instructions, version, manifest, rights/attribution notes, and known limitations.
8. `listing_packet` — prepare internal-only title, description, screenshots/preview references, tags, compatibility, price research, and disclosures. Do not publish.
9. `ceo_review` — department handoff and CEO recommendation; then owner decision for internal acceptance. Internal acceptance is not marketplace approval.

Every stage must record its responsible role/agent, status, start/completion timestamps, input and output references, evidence, blockers, and cost estimate. The total approved provider budget is USD 0 unless the owner explicitly changes it. External actions remain disabled in persisted policy, not merely hidden in the UI.

## Data and persistence requirements

- Persist product workflow and stage records using the existing SQLiteStore connection, transaction lock, and append-only audit-event mechanism.
- Every workflow is assigned to exactly one commercial business unit; the pilot uses `digital-products`.
- Store immutable workflow-to-business ownership and validate all linked work items, artifacts, and deliverables against that same business unit.
- Use stable artifact IDs and a managed artifact root. Resolve paths beneath that root and reject traversal, symlinks escaping the root, unexpected file types, and oversized archives.
- Store content hashes and provenance for every generated artifact. Do not store only arbitrary paths or unverified URLs.
- Record transitions and QA outcomes as audit events in the same transaction as the state change.
- A failed QA result preserves evidence and permits a controlled return to production; downstream stage results must be invalidated when their inputs change.
- A workflow cannot be approved while required stages are pending, blocked, or failed.
- An approved internal workflow cannot enable publishing, customer messaging, purchases, spending, payment operations, or account changes.

## Agent execution contract

- Use the existing CEO → department manager → specialist delegation system; do not create a parallel collection of pretend-running agents.
- Route Product & Innovation work through the canonical `product-innovation` department and role contracts. Validate role activation, task assignment, approval, and business scope before queue admission.
- Agent prompts must receive the actual product brief, current stage, acceptance criteria, constraints, prior stage evidence, artifact references, and a structured output contract.
- AI-generated text stages may use only an owner-configured, currently eligible zero-cost provider. Record provider/model and provider-reported usage. If no eligible provider exists, leave the stage blocked with a clear reason; never claim execution.
- File creation should prefer deterministic local generators and standard-library tooling. Model output is not a substitute for binary asset generation, visual QA, engine validation, or rights review.
- Generated deliverables remain review-required. The CEO may request rework; only the owner can approve protected external actions.

## Pilot: OUTPOST Sci-Fi Survival UI Icon Pack

The repository tree on the current OpenCompany branch does not contain the referenced OUTPOST source package. A Library search found the unpublished listing draft and business notes, but not the claimed SVG/PNG archive or preview files. The listing draft describes an intended inventory of 30 SVGs, 30 icons exported at 512/256/128 px, a 6×5 atlas, dark/light previews, a manifest, and import notes; these are draft claims, not verified files. Do not claim that the existing package has been inspected or validated. First locate the original files in an accessible repository/library attachment or create a new original pilot from a documented brief. If the source is unavailable, record that as a blocker and request only the missing source or permission to create a clean replacement.

The pilot's completion report must separate:
- generated files and reproducible hashes;
- automated checks actually executed;
- visual/functional checks not yet performed;
- target-engine compatibility not yet tested;
- licensing/IP review not performed;
- market-demand evidence and remaining uncertainty.

A ZIP that passes integrity checks is a valid archive, not proof of a customer-ready game asset pack.

## API and dashboard contract

Expose owner-authenticated create/list/detail/transition/rework/review/download operations through the current router composition. Dashboard actions must reflect server-side state and explain blockers. Every route must use the canonical owner authentication and CSRF/session safeguards. Never create a second authentication implementation.

The dashboard must show business unit, current stage, progress, assigned role, cost ceiling/actual reported cost, blockers, evidence, artifact downloads, QA result, and approval state. Label prototypes and untested claims plainly.

## Non-goals and release gates

- No production routing, Railway, Vercel, database, or secret changes.
- No tests or CI before 2026-12-01 unless the owner changes the existing deferral.
- No paid provider, metered generation, subscription, marketplace fee, purchase, or hosting spend.
- No public listing, publishing, customer contact, customer commitment, payment action, or account change.
- No automatic merge or deployment.
- Do not call a role profile a running agent without verified execution records and outputs.

## Definition of done

1. A single owner-authenticated API/dashboard workflow starts and tracks a business-scoped product job.
2. Product & Innovation agents execute through the existing approval-gated work orchestration.
3. Product files are generated without owner-supplied source files when the brief is sufficient, using no-cost deterministic tooling where possible.
4. Artifact storage is safe, downloadable, reproducible, and linked to the product record.
5. QA evidence is reproducible; failures block completion and enable controlled rework.
6. Human preview and untested visual, compatibility, legal, and demand claims remain explicit.
7. CEO review and owner approval are enforced; external actions remain disabled.
8. Documentation distinguishes implemented, executed, and unverified capabilities.
9. Tests are added for the workflow but remain unrun during the owner's testing pause.
