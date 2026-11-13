"""Opt-in, approval-preserving Product & R&D background coordinator.

The coordinator may create unassigned draft work items, synchronize deliverables
that have already passed owner review, and run the local deterministic OUTPOST
prototype generator. It never approves a delegation proposal, admits work to the
worker queue, starts model inference, or performs external business actions.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .domain import AgentState, AuditRecord, TaskState, WorkItem
from .product_artifacts import generate_outpost_pack
from .product_rd import PRODUCT_STAGES
from .product_rd import ProductRDRepository
from .manager_ai import recommend_department_plan

logger = logging.getLogger(__name__)

SYSTEM_ACTOR = "product_rd_coordinator"
MODEL_STAGES = set(PRODUCT_STAGES) - {"artifact_generation", "automated_qa", "human_preview"}


def _artifact_root() -> Path:
    return Path(os.environ.get("OPENCOMPANY_PRODUCT_ARTIFACT_ROOT", "data/product-artifacts")).expanduser()


class ProductRDCoordinator:
    """Perform only deterministic or already-owner-approved internal transitions."""

    def __init__(self, store, *, artifact_root: Path | None = None, delegations=None,
                 gateway=None, auto_manager_proposals_enabled: bool = False) -> None:
        self.store = store
        self.repo = ProductRDRepository(store._connection, store._lock)
        self.delegations = delegations
        self.gateway = gateway
        self.auto_manager_proposals_enabled = bool(auto_manager_proposals_enabled)
        self.artifact_root = artifact_root or _artifact_root()

    def run_once(self) -> dict[str, int]:
        stats = {"work_items_drafted": 0, "manager_proposals_prepared": 0,
                 "stages_synchronized": 0, "pilot_packs_generated": 0,
                 "blocked_or_skipped": 0}
        for workflow in self.repo.list(limit=100):
            try:
                stage = next((item for item in workflow["stages"]
                              if item["status"] == "in_progress"), None)
                if stage is None:
                    continue
                if stage["key"] == "artifact_generation":
                    if (workflow["business_id"] == "digital-products"
                            and "outpost" in workflow["title"].casefold()):
                        if self._generate_outpost(workflow, stats):
                            continue
                    stats["blocked_or_skipped"] += 1
                    continue
                if stage["key"] in MODEL_STAGES:
                    if stage.get("work_item_id"):
                        if self._sync_if_owner_approved(workflow, stage):
                            stats["stages_synchronized"] += 1
                        elif self._prepare_manager_proposal(workflow, stage):
                            stats["manager_proposals_prepared"] += 1
                    elif self._draft_stage_work_item(workflow, stage):
                        stats["work_items_drafted"] += 1
                    else:
                        stats["blocked_or_skipped"] += 1
            except Exception as exc:
                stats["blocked_or_skipped"] += 1
                logger.warning(
                    "Product R&D coordinator skipped workflow=%s stage=%s error_type=%s",
                    workflow.get("id"), stage.get("key") if stage else "unknown",
                    type(exc).__name__,
                )
        return stats

    def _draft_stage_work_item(self, workflow: dict, stage: dict) -> bool:
        role_key = stage["owner_role"]
        from .organization import default_organization
        from .workforce import default_workforce

        with self.store._lock:
            current = self.repo.get(workflow["id"])
            if current is None:
                return False
            active = next((s for s in current["stages"] if s["status"] == "in_progress"), None)
            if active is None or active["key"] != stage["key"] or active.get("work_item_id"):
                return False
            profiles = self.store.list_agents(limit=1000)
            agent = next((a for a in profiles if a.role_key == role_key
                          and a.state == AgentState.ACTIVE), None)
            if agent is None:
                return False
            try:
                spec = default_organization().get(agent.department)
                if role_key not in spec.role_keys:
                    return False
                expected_team = (
                    "executive" if role_key == "chief_executive_orchestrator"
                    else "management" if role_key == spec.manager_role_key
                    else default_workforce().get(role_key).team_key
                )
            except LookupError:
                return False
            if agent.team_key != expected_team:
                return False

            prior = [s for s in current["stages"] if s["status"] == "completed"][-3:]
            prior_context = json.dumps([
                {"stage": s["key"], "output": (s.get("output") or "")[:700],
                 "evidence": s.get("evidence", [])[:4],
                 "artifact_refs": s.get("artifact_refs", [])[:4]}
                for s in prior
            ], ensure_ascii=False)[:3500]
            objective = (
                f"OpenCompany Product & R&D workflow {current['id']}. "
                f"Business unit: {current['business_id']}. Stage: {stage['key']}. "
                f"Product: {current['title']}. Product brief: {current['brief'][:6000]}. "
                f"Prior approved stage context: {prior_context}. "
                "Create an internal evidence-backed draft only. Include method, findings, "
                "assumptions, limitations, and handoff. Distinguish sourced facts from "
                "assumptions. Do not contact customers, publish, purchase, spend, or alter accounts. "
                "Use only confirmed zero-cost resources."
            )
            direct_ceo = role_key == "chief_executive_orchestrator"
            item = WorkItem(
                id=uuid4(),
                title=f"Product R&D · {stage['key']} · {current['title']}"[:240],
                objective=objective,
                department=agent.department,
                state=TaskState.DRAFT,
                assigned_agent_id=agent.id if direct_ceo else None,
                business_id=current["business_id"],
            )
            event = AuditRecord(
                id=uuid4(), occurred_at=datetime.now(timezone.utc),
                actor_type="system", actor_id=SYSTEM_ACTOR,
                action="product_rd.stage_work_item_drafted",
                subject_type="work_item", subject_id=str(item.id),
                outcome="drafted", correlation_id=str(current["id"]),
                details={"workflow_id": str(current["id"]), "stage": stage["key"],
                         "business_id": current["business_id"], "agent_id": str(agent.id),
                         "role_key": role_key, "owner_approval_required": True},
            )
            self.store.save_work_item_with_audit(item, event)
            self.repo.attach_work_item(
                current["id"], stage["key"], str(item.id),
                actor_id=SYSTEM_ACTOR, actor_type="system",
            )
            return True

    def _prepare_manager_proposal(self, workflow: dict, stage: dict) -> bool:
        """Persist one AI manager recommendation; never approve or enqueue it."""
        if (not self.auto_manager_proposals_enabled or self.gateway is None
                or self.delegations is None or not stage.get("work_item_id")):
            return False
        item = self.store.get_work_item(UUID(stage["work_item_id"]))
        if (item is None or item.business_id != workflow["business_id"]
                or item.state != TaskState.DRAFT or item.assigned_agent_id is not None):
            return False
        # Existing proposals are an idempotency boundary; never replace owner decisions.
        if self.delegations.list_for_parent(item.id):
            return False
        from .organization import default_organization
        from .domain import AgentState
        try:
            department = default_organization().get(item.department)
        except LookupError:
            return False
        profiles = self.store.list_agents(limit=1000)
        manager = next((agent for agent in profiles
                        if agent.role_key == department.manager_role_key
                        and agent.department == item.department), None)
        if (manager is None or manager.state != AgentState.ACTIVE
                or manager.team_key != "management"):
            return False
        recommendation = recommend_department_plan(item, self.gateway, max_specialists=15)
        plan = recommendation.plan
        children = []
        if plan.mode.value == "manager_direct":
            children.append({
                "assigned_agent_id": str(manager.id), "role_key": plan.manager_role_key,
                "team_key": "management", "title": f"{plan.manager_title}: {item.title}",
                "objective": f"Handle parent work item {item.id}. Objective: {item.objective} Produce an internal draft for owner review.",
            })
        elif plan.mode.value == "specialist_team":
            for specialist in plan.specialists:
                profile = next((agent for agent in profiles
                                if agent.role_key == specialist.role_key
                                and agent.team_key == specialist.team_key
                                and agent.department == item.department), None)
                if (profile is None or profile.state != AgentState.ACTIVE
                        or profile.role_key != specialist.role_key
                        or profile.team_key != specialist.team_key
                        or profile.department != item.department):
                    return False
                children.append({
                    "assigned_agent_id": str(profile.id), "role_key": specialist.role_key,
                    "team_key": specialist.team_key, "title": f"{specialist.title}: {item.title}",
                    "objective": (
                        f"Support parent work item {item.id}. Parent objective: {item.objective} "
                        f"Manager rationale: {recommendation.rationale} "
                        f"Required capabilities: {', '.join(recommendation.required_capabilities)}. "
                        "Produce an internal draft for manager review only."
                    ),
                })
        # Persist owner_review plans too, so unresolved scope is not replanned every tick.
        self.delegations.create_proposal(
            parent_work_item_id=item.id,
            request={
                "required_capabilities": list(recommendation.required_capabilities),
                "max_specialists": 15,
                "manager_rationale": recommendation.rationale,
                "planner_provider": recommendation.provider,
                "planner_model": recommendation.model,
                "selected_team_keys": list(dict.fromkeys(
                    specialist.team_key for specialist in plan.specialists
                )),
                "created_by": SYSTEM_ACTOR,
            },
            manager_agent_id=manager.id, mode=plan.mode.value,
            team_key=plan.selected_team_key, children=children,
        )
        return True
    def _sync_if_owner_approved(self, workflow: dict, stage: dict) -> bool:
        from .organization import default_organization
        from .workforce import default_workforce

        item_id = stage.get("work_item_id")
        if not item_id:
            return False
        item = self.store.get_work_item(UUID(item_id))
        if item is None or item.business_id != workflow["business_id"] or item.state != TaskState.COMPLETED:
            return False
        assigned = self.store.get_agent(item.assigned_agent_id) if item.assigned_agent_id else None
        if assigned is None or assigned.state != AgentState.ACTIVE or assigned.department != item.department:
            return False
        try:
            department = default_organization().get(item.department)
        except LookupError:
            return False
        direct_owner = assigned.role_key == stage["owner_role"]
        manager_synthesis = assigned.role_key == department.manager_role_key
        if not direct_owner and not manager_synthesis:
            return False
        try:
            expected_team = (
                "executive" if assigned.role_key == "chief_executive_orchestrator"
                else "management" if manager_synthesis
                else default_workforce().get(assigned.role_key).team_key
            )
        except LookupError:
            return False
        if assigned.team_key != expected_team:
            return False
        if manager_synthesis and not direct_owner:
            if not item.depends_on:
                return False
            for dependency_id in item.depends_on:
                dependency = self.store.get_work_item(dependency_id)
                if (dependency is None or dependency.business_id != workflow["business_id"]
                        or dependency.state != TaskState.COMPLETED
                        or not self.store.list_deliverables(dependency_id)):
                    return False
        deliverables = self.store.list_deliverables(item.id)
        if not deliverables:
            return False
        deliverable = deliverables[-1]
        self.repo.complete_stage(
            workflow["id"], stage["key"],
            output=deliverable["content"][:12000],
            evidence=[
                f"Owner-approved work item: {item.id}",
                f"Review-required deliverable: {deliverable['id']}",
                f"Provider/model: {deliverable['provider']}/{deliverable['model']}",
                f"Recorded inference cost: USD {float(deliverable['cost_usd']):.6f}",
            ],
            artifact_refs=[f"work-item:{item.id}", f"deliverable:{deliverable['id']}"],
            cost_actual_usd=float(deliverable["cost_usd"]),
            actor_id=SYSTEM_ACTOR, actor_type="system",
        )
        return True

    def _generate_outpost(self, workflow: dict, stats: dict[str, int]) -> bool:
        generated = generate_outpost_pack(str(workflow["id"]), self.artifact_root)
        refs = [item["download_url"] for item in generated["artifacts"]]
        self.repo.complete_stage(
            workflow["id"], "artifact_generation",
            output="Generated the deterministic original 30-icon SVG prototype, contact sheet, manifest, README, draft license notice, and ZIP archive.",
            evidence=[
                f"Generated {len(generated['artifacts'])} artifact files.",
                "Generation used deterministic local code; no model call or external service was used.",
                *[f"artifact:{entry['name']};sha256:{entry['sha256']};size_bytes:{entry['size_bytes']}"
                  for entry in generated["artifacts"]],
            ],
            artifact_refs=refs, actor_id=SYSTEM_ACTOR, actor_type="system",
        )
        qa = generated["qa"]
        self.repo.complete_stage(
            workflow["id"], "automated_qa",
            output="Deterministic archive, manifest, file-count, and SVG-XML checks completed.",
            evidence=qa["passed_checks"] or qa["failed_checks"] or ["No QA checks were reported."],
            artifact_refs=refs, qa_result=qa,
            actor_id=SYSTEM_ACTOR, actor_type="system",
        )
        stats["pilot_packs_generated"] += 1
        return True
