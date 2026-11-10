"""Owner-triggered creation of one draft manager profile per department."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

from .domain import AgentProfile, AgentState, AuditRecord
from .organization import default_organization
from .persistence import SQLiteStore
from .workforce import default_workforce, specialist_role_keys


def bootstrap_department_managers(store: SQLiteStore) -> tuple[AgentProfile, ...]:
    """Create missing manager profiles idempotently; never activate them."""
    workforce = default_workforce()
    created_or_existing = []
    existing_ids = {item.id for item in store.list_agents(limit=1000)}
    for department in default_organization().all():
        role = workforce.get(department.manager_role_key)
        agent_id = uuid5(
            NAMESPACE_URL,
            f"opencompany:department-manager:{department.key}:{role.key}",
        )
        if agent_id not in existing_ids:
            profile = AgentProfile(
                id=agent_id,
                name=f"{department.name} Manager",
                department=department.key,
                purpose=department.mission,
                capabilities=role.capabilities,
                state=AgentState.DRAFT, role_key=role.key, team_key="management",
            )
            now = datetime.now(timezone.utc)
            event = AuditRecord(
                id=uuid4(), occurred_at=now,
                actor_type="owner", actor_id="owner",
                action="agent.manager_profile_created",
                subject_type="agent_profile", subject_id=str(agent_id),
                outcome="created_draft", correlation_id=str(uuid4()),
                details={
                    "department": department.key,
                    "role_key": role.key,
                    "state": AgentState.DRAFT.value,
                },
            )
            store.save_agent_with_audit(profile, event)
            existing_ids.add(agent_id)
        saved = store.get_agent(agent_id)
        if saved is not None:
            created_or_existing.append(saved)
    return tuple(created_or_existing)



def bootstrap_specialist_profiles(store: SQLiteStore) -> tuple[AgentProfile, ...]:
    """Create 250 specialist profiles as drafts; never activate workers."""
    workforce = default_workforce()
    created_or_existing = []
    existing_ids = {item.id for item in store.list_agents(limit=1000)}
    for department in default_organization().all():
        for role_key in specialist_role_keys(department.key):
            role = workforce.get(role_key)
            agent_id = uuid5(NAMESPACE_URL, f"opencompany:specialist:{department.key}:{role.key}")
            if agent_id not in existing_ids:
                profile = AgentProfile(
                    id=agent_id,
                    name=role.title,
                    department=department.key,
                    purpose=role.mission,
                    capabilities=role.capabilities,
                    state=AgentState.DRAFT, role_key=role.key, team_key=role.team_key,
                )
                now = datetime.now(timezone.utc)
                event = AuditRecord(
                    id=uuid4(), occurred_at=now,
                    actor_type="owner", actor_id="owner",
                    action="agent.specialist_profile_created",
                    subject_type="agent_profile", subject_id=str(agent_id),
                    outcome="created_draft", correlation_id=str(uuid4()),
                    details={
                        "department": department.key,
                        "role_key": role.key,
                        "state": AgentState.DRAFT.value,
                    },
                )
                store.save_agent_with_audit(profile, event)
                existing_ids.add(agent_id)
            saved = store.get_agent(agent_id)
            if saved is not None:
                created_or_existing.append(saved)
    return tuple(created_or_existing)



def bootstrap_executive_orchestrator(store: SQLiteStore) -> AgentProfile:
    """Create the owner-subordinate CEO/orchestrator profile as a draft."""
    workforce = default_workforce()
    role = workforce.get("chief_executive_orchestrator")
    agent_id = uuid5(NAMESPACE_URL, "opencompany:executive:chief-executive-orchestrator")
    existing = store.get_agent(agent_id)
    if existing is not None:
        return existing
    profile = AgentProfile(
        id=agent_id,
        name=role.title,
        department="executive-office",
        purpose=role.mission,
        capabilities=role.capabilities,
        state=AgentState.DRAFT, role_key=role.key, team_key="executive",
    )
    event = AuditRecord(
        id=uuid4(), occurred_at=datetime.now(timezone.utc),
        actor_type="owner", actor_id="owner",
        action="agent.executive_profile_created",
        subject_type="agent_profile", subject_id=str(agent_id),
        outcome="created_draft", correlation_id=str(uuid4()),
        details={"role_key": role.key, "state": AgentState.DRAFT.value},
    )
    store.save_agent_with_audit(profile, event)
    saved = store.get_agent(agent_id)
    if saved is None:
        raise RuntimeError("executive orchestrator profile was not persisted")
    return saved
