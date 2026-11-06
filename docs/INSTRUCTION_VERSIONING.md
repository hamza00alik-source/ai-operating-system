# Versioned Agent Instructions

## Design

Agency Agents Markdown profiles remain pinned, read-only source material. The OS adds a separate, versioned instruction addendum per specialist; it never edits upstream profiles. The addendum is inserted into specialist work packets after the role profile and before the OS governance block. The CEO/owner governance block remains higher priority.

Each agent receives a deterministic empty baseline snapshot (v1) bound to the SHA-256 hash of its upstream profile. The baseline is materialized as an immutable SQLite row when the first addendum is activated, avoiding database writes during ordinary work-packet creation. An active head points to one immutable version. Activating a change creates a new version with its own content hash, parent version, source proposal, actor, and timestamp. Existing versions are never edited or deleted.

## Adoption flow

1. A specialist report is evaluated and repeated failures may lead the CEO proposal generator to draft a candidate.
2. The owner approves the proposal for testing.
3. The static text/policy screen checks the exact proposal text and stores a content hash.
4. The owner explicitly selects **Activate tested version**. The API requires the latest test to have passed and its SHA-256 to match the current proposal text.
5. The activation creates a new immutable version and moves the active head. The API call is owner-authenticated and hash-chain audited.
6. The owner can select **Rollback agent instructions**. Rollback moves the active head to the immutable parent version; no version history is deleted.

Testing alone never activates anything. CEO proposal generation never activates anything. There is no background auto-adoption.

## Profile drift and precedence

Every instruction version is bound to the exact upstream profile hash. If the pinned profile changes, the active addendum is withheld from work packets and activation/rollback is blocked until the baseline is reviewed. This prevents an addendum tested against one upstream role profile from silently being applied to a different profile.

The addendum is not a security boundary. Imported profile instructions and addenda cannot grant tools or permissions. OS governance is appended after the addendum and remains higher priority. Actual permissions must still be enforced by runtime/tool gateways.

## Limits

The current test stage is static text screening, not an isolated LLM behavior benchmark. It does not compare model outputs with baseline vs candidate instructions. Activation therefore requires both a passing narrow static screen and an explicit owner action, but should be treated as a controlled instruction rollout—not proof of improved model behavior. Provider-backed A/B testing remains disabled until a genuinely isolated, no-tools model evaluation environment and task-specific datasets are implemented.

The active addendum is used by work packets and therefore by the specialist worker path that consumes those packets. This does not mean the model provider is configured or that any agents are running by default. No paid provider is enabled by this feature.
