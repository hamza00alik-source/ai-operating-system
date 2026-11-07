# Continuous Learning and Evaluation

## Current capability

The company has a persistent, source-attributed knowledge store. Specialist agents can propose knowledge candidates from URLs present in their task context. New candidates remain untrusted until the owner accepts them. Agents can retrieve only owner-accepted notes, within bounded context limits. Retrieval removes exact duplicates by normalized source URL, title, and content; publication-date freshness is used only as a tie-breaker and is explicitly labeled a heuristic. Retrieval remains lexical rather than semantic.

This release adds a deterministic report-evaluation rubric and a small regression dataset. The evaluator checks:
- JSON-object shape, allowed status, and non-empty summary;
- evidence and blocker field types;
- evidence on completed reports and reasons on blocked reports;
- explicit claims that an agent performed external actions that the current runtime cannot perform.

The fixture dataset is exercised in CI without calling a model provider. It is intended as a stable baseline for future evaluation work.

## What a passing evaluation means

A passing result means only that the report met these structural and explicit safety checks. It does **not** establish factual accuracy, source authenticity, reasoning quality, market demand, or completeness. Those require source-aware and task-specific evaluation datasets, and eventually owner review.

Trend labels are deliberately cautious (`provisional_regression`, `provisional_improvement`, `no_clear_change`, or `insufficient_data`). A score change of at least five points sets a provisional signal; it does not automatically diagnose agent quality or trigger a change.

The evaluator itself remains a pure, provider-free function. Each model-backed specialist execution now stores its evaluation in SQLite, linked to the exact company run, step, and agent, with evaluator version, score, pass/fail result, individual checks, limitations, and timestamp. The owner-protected `GET /evaluations` endpoint returns bounded history and a summary; optional `agent_id` and `run_id` filters are supported. Evaluation records are included in the verified SQLite backup schema.

## Next stages

1. Add semantic retrieval/embeddings and task-specific datasets with expected evidence and rubric criteria.
2. Persist evaluation outcomes with the run, specialist, evaluator version, and timestamp.
3. Track quality trends across repeated tasks and detect regressions. The owner API and dashboard now compare the latest five evaluations with the previous five per agent; fewer than ten evaluations produce no signal. Signals are provisional because task difficulty is not recorded or normalized.
4. Let the CEO propose prompt/workflow improvements with evidence and expected impact. The current deterministic proposal generator drafts suggestions only after the same known rubric check fails at least twice for an agent in the recent evaluation sample. Owners can approve a proposal for testing or reject it; approval does not adopt or activate the change.
5. Run candidate changes against the regression suite; keep the current version active on failure.
6. Version specialist instruction addenda, require an owner activation action, and preserve rollback history. The first implementation is now available: immutable per-agent versions are bound to the upstream profile hash; the owner can activate only the exact proposal text whose latest static test passed; activation is audited; rollback restores the parent version without deleting history.
7. Build a true isolated model-behavior regression environment with task-specific datasets before treating any change as empirically improved.

No automatic self-modification, autonomous policy changes, paid inference, or external actions are enabled by this evaluator. Proposal generation is rule-based and advisory. Owner-approved candidates pass through deterministic static text/policy checks for instruction overrides, approval bypasses, unrestricted execution, unauthorized external-action language, candidate size, and supporting evaluation evidence. Results are immutable records with a screening-policy version label and candidate hash. An optional local-only baseline-vs-candidate behavior harness is now available: it requires an explicit owner-token request, local OpenAI-compatible HTTP inference, no API key, and no CLI/remote endpoint. It compares two reports against fixed fixtures, persists hashes/scores/checks, and never activates a candidate. If a behavior test exists, activation requires the latest result to pass for the exact candidate text and same active baseline version. This remains a limited regression signal, not proof of factual quality or general model improvement. If no local model is configured, the static screen plus separate owner-token activation path remains available. The active addendum is subordinate to OS governance and is withheld if the pinned upstream profile hash changes. See [INSTRUCTION_VERSIONING.md](INSTRUCTION_VERSIONING.md) and [BEHAVIOR_TESTING.md](BEHAVIOR_TESTING.md).
