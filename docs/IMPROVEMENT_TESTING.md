# Isolated Improvement Testing

An owner may approve a CEO improvement proposal for testing. The current test stage performs a deterministic static screen of the proposed instruction text and its evidence metadata.

## What is checked

- Candidate text is present and within the configured size limit.
- At least two linked evaluation records support the proposal.
- Candidate text does not contain known instruction-override, owner-approval-bypass, unrestricted-execution, or unauthorized-external-action patterns.
- Each test run records the screening policy version label, candidate SHA-256, individual checks, result, and limitations.

## Important boundary

This is a **static text/policy contract screen**, not an LLM A/B test, sandbox, or behavioral benchmark. It does not load or compare the live agent profile, invoke a model, prove that a model will obey an instruction, or verify factual quality. A pass means only that the candidate text passed these narrow checks.

Test results are append-only history. Running tests does not change the proposal status, active agent profiles, prompts, tools, or runtime permissions. A failed test leaves the current behavior untouched. A passing test is not adoption approval. There is no adoption endpoint or automatic activation.

Before any future adoption system, the project still needs versioned baseline instructions, an isolated model-behavior evaluation environment, task-specific regression datasets, rollback support, and a separate owner-authorized activation workflow.

The screening policy version is a version label for these static checks, **not** a versioned copy of the live agent instructions.
