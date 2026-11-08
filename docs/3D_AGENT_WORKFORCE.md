# 3D AI Workforce — Architecture and Delivery Plan

**Status:** design foundation only. This document does not claim that 3D rendering, avatars, or live event streaming are implemented.

## Product decision

Build a realistic, professional, hybrid corporate/futuristic headquarters with two complementary experiences:

1. **Operations dashboard:** fast, accessible, low-bandwidth overview of the company.
2. **3D headquarters:** optional immersive view where the owner can inspect departments, select an agent, and open that agent's real task/activity panel.

The 3D view is a presentation client, not an agent runtime. The existing AIOS backend remains the source of truth for identities, tasks, workflow state, approvals, and audit history.

## Non-negotiable constraints

- Keep the 3D client separate from the existing Python API and worker runtime.
- No model calls, tools, publishing, spending, customer contact, order actions, or approval decisions originate from avatar animation or scene interaction.
- All consequential actions continue through existing authenticated API and approval workflows.
- Do not fabricate activity. If the backend has no event for an agent, show **Unknown / no recent activity**, not "working".
- Provide a 2D/list fallback for low-end Android devices, reduced motion, WebGL failure, and low bandwidth.
- Load only visible/selected avatars; use level-of-detail, instancing where appropriate, compressed textures, lazy loading, and a capped frame rate on mobile.
- Start with free/open-source assets and tools. No paid asset, hosting, API, or metered rendering dependency without owner approval.
- Avatar assets must be original or properly licensed. Do not copy protected game characters or likenesses.
- Never describe a static image as a rigged or interactive 3D model.

## Proposed technical shape

- **Backend:** existing AIOS Python API and database. Add read-only presentation endpoints only after inspecting the current API/auth models.
- **Event transport:** begin with authenticated polling or server-sent events if supported by the deployment. WebSocket is optional, not a prerequisite.
- **Web client:** a separately deployable browser client. Evaluate Three.js (or React Three Fiber only if the repository's frontend stack supports React) before selecting the renderer.
- **Avatar interchange:** glTF 2.0 / GLB for rigged models and animation clips. VRM may be supported as an optional profile format if licensing and runtime compatibility are confirmed.
- **Authoring:** Blender for rigging/optimization; do not require the owner to install or operate Blender.
- **Mobile-first:** responsive UI, touch selection, low-poly/LOD avatar variants, texture budgets, and a non-3D fallback.

## Runtime identity and avatar contract

The visual client must consume a stable, backend-issued agent identity. Suggested read-only presentation object:

```json
{
  "agent_id": "stable-agent-id",
  "display_name": "Research Lead",
  "department_id": "research",
  "role": "department_lead",
  "avatar": {
    "asset_id": "research-lead-v1",
    "asset_url": "/assets/avatars/research-lead-v1.glb",
    "profile": "humanoid-realistic",
    "lod": ["low", "medium", "high"]
  },
  "presence": {
    "state": "working",
    "state_source": "worker_event",
    "observed_at": "2026-01-01T00:00:00Z",
    "task_id": "task-id-or-null"
  }
}
```

This is a proposed DTO, not an existing API response. The implementation must map it from real repository models and omit fields that cannot be verified.

## Presence state mapping

| Backend evidence | Visual treatment | Important rule |
|---|---|---|
| Active leased task / worker heartbeat | Working animation | Must be derived from current worker state |
| Explicit idle / available record | Idle animation | Do not infer from missing tasks |
| Task completed event | Brief success animation, then idle | Completion comes from persisted task state |
| Task failed / blocked | Attention state | Show reason in accessible text |
| Approval pending | Owner-review indicator | Avatar cannot approve it |
| Worker heartbeat stale | Offline / stale indicator | Do not show as active |
| No reliable state | Unknown | Never invent presence |

Animation is decorative and must not be treated as evidence of execution.

## Initial scene and cast

Create one compact headquarters scene with these areas:
- CEO office / owner command centre
- Research
- Engineering
- Quality and security
- Commerce and operations

Initial detailed avatars:
1. CEO / orchestration representative
2. Research lead
3. Engineering lead
4. Quality and security lead
5. Commerce / operations lead

The exact agent IDs must be discovered from the existing registry. Do not create duplicate agents just to populate the scene. The remaining registered specialists use lightweight roster entries and shared/low-detail avatar rigs until selected.

## Interaction model

- Tap an agent to open a profile panel: identity, department, current task, latest verified event, heartbeat age, and task history.
- Tap a department to filter its registered agents and tasks.
- "Talk to agent" opens the existing authenticated AIOS conversation/task workflow; it does not create a separate untracked chat runtime.
- Approval requests link to the existing approval inbox. Approval is never completed by clicking an avatar.
- Provide keyboard navigation, screen-reader labels, captions/status text, reduced-motion support, and a 2D roster equivalent.

## Security and privacy

- Read-only scene endpoints must use the same authentication and authorization policy as the operational API.
- Never expose API keys, provider credentials, private prompts, raw chain-of-thought, customer personal data, or secret tool arguments in scene payloads.
- Return concise task summaries and safe status metadata only.
- Enforce owner/role access on any action routed from the visual client.
- Log actual consequential actions through the existing audit system, not client-side animation events.

## Delivery milestones

### M0 — Repository fit and data mapping
- Inspect current API routes, agent registry, worker/task models, auth, and frontend status.
- Confirm canonical agent IDs and event sources.
- Decide renderer only after repository/frontend inspection.
- Add tests for DTO mapping and redaction.

### M1 — Read-only 2D workforce roster
- Authenticated read-only endpoint for agents and verified presence.
- Department filters, stale/unknown states, task links.
- Mobile-friendly roster; no 3D assets required.

### M2 — 3D proof of concept
- One optimized, properly licensed rigged GLB avatar.
- One small room and touch selection.
- Use mocked fixtures only in isolated development/demo mode; visibly label demo data.
- No production activity claims until connected to real backend events.

### M3 — Live read-only integration
- Map real agent/task/heartbeat records to presence DTO.
- Poll/SSE with reconnect, stale-state handling, and bounded payloads.
- Security, auth, and redaction tests.

### M4 — Department expansion
- Add department environments and avatar variants.
- Lazy-load selected/visible models; provide 2D fallback.
- Expand visual profiles to the full agent registry without loading all models simultaneously.

### M5 — Conversation and workflow deep links
- Route user-initiated interactions through existing authenticated AIOS task/conversation APIs.
- Preserve approval gates and audit events.
- No direct side-effecting integrations from the 3D client.

## Acceptance criteria

- 3D view is optional and can be disabled without affecting AIOS.
- Every displayed agent maps to one real registry identity.
- Presence is backed by timestamped backend evidence; stale and unknown states are explicit.
- The owner can use the full essential workflow from the 2D fallback on Android.
- No avatar animation can trigger an external action or bypass approval.
- No paid dependency is introduced.
- Automated tests cover identity mapping, presence freshness, redaction, authorization, and approval isolation.
- A real rigged GLB is validated in the target browser before claiming a 3D avatar milestone complete.

## Immediate next engineering step

Inspect the active implementation branch and repository models before coding endpoints or choosing a frontend framework. This branch intentionally adds the architecture decision first; it does not merge into `main` or deploy anything.
