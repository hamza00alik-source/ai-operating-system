import pytest
from opencompany.permissions import Action
from opencompany.skills import Skill, SkillRegistry


def test_registered_skill_executes_only_declared_action():
    registry = SkillRegistry()
    registry.register(
        Skill("market_scan", "Find evidence", "Search public sources",
              (Action.RESEARCH.value,), ()),
        lambda payload: {"query": payload["query"], "items": 2},
    )
    result = registry.execute("market_scan", "research", {"query": "buyer demand"})
    assert result.output == {"query": "buyer demand", "items": 2}
    assert result.skill_key == "market_scan"
    assert result.skill_version == 1


def test_skill_catalog_is_sorted_and_does_not_expose_handlers():
    registry = SkillRegistry()
    registry.register(
        Skill("zeta", "Second", "Internal procedure", (Action.READ.value,), ()),
        lambda payload: payload,
    )
    registry.register(
        Skill("alpha", "First", "Another internal procedure",
              (Action.RESEARCH.value,), ()),
        lambda payload: payload,
    )
    catalog = registry.list()
    assert [item["key"] for item in catalog] == ["alpha", "zeta"]
    assert catalog[0] == {
        "key": "alpha",
        "purpose": "First",
        "version": 1,
        "allowed_actions": ["research"],
        "approval_actions": [],
    }
    assert "procedure" not in catalog[0]
    assert "handler" not in catalog[0]


def test_skill_cannot_execute_action_outside_its_scope():
    called = []
    registry = SkillRegistry()
    registry.register(
        Skill("draft", "Create drafts", "Prepare an internal draft",
              (Action.CREATE_DRAFT.value,), ()),
        lambda payload: called.append(payload),
    )
    with pytest.raises(PermissionError, match="outside skill scope"):
        registry.execute("draft", "publish", {})
    assert called == []


def test_sensitive_skill_action_requires_owner_approval():
    called = []
    registry = SkillRegistry()
    registry.register(
        Skill("publisher", "Publish", "Publish approved content",
              (Action.PUBLISH.value,), (Action.PUBLISH.value,)),
        lambda payload: called.append(payload) or "published",
    )
    with pytest.raises(PermissionError, match="approval required"):
        registry.execute("publisher", "publish", {"id": "draft-1"})
    assert called == []
    result = registry.execute(
        "publisher", "publish", {"id": "draft-1"}, owner_approved=True
    )
    assert result.output == "published"
    assert called == [{"id": "draft-1"}]


def test_registry_rejects_duplicate_keys_and_unknown_actions():
    registry = SkillRegistry()
    skill = Skill("read", "Read", "Read public data", (Action.READ.value,), ())
    registry.register(skill, lambda payload: payload)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(skill, lambda payload: payload)
    with pytest.raises(ValueError, match="Unknown skill action"):
        Skill("bad", "Bad", "Bad action", ("execute_anything",), ()).validate()


def test_worker_adapter_ignores_approval_claim_in_job_payload():
    called = []
    registry = SkillRegistry()
    registry.register(
        Skill("publisher", "Publish", "Publish approved content",
              (Action.PUBLISH.value,), (Action.PUBLISH.value,)),
        lambda payload: called.append(payload) or {"published": True},
    )
    handler = registry.worker_handler("publisher", "publish")
    with pytest.raises(PermissionError, match="approval required"):
        handler({"draft_id": "d1", "owner_approved": True})
    assert called == []


def test_worker_adapter_uses_only_trusted_approval_resolver():
    registry = SkillRegistry()
    registry.register(
        Skill("publisher", "Publish", "Publish approved content",
              (Action.PUBLISH.value,), (Action.PUBLISH.value,)),
        lambda payload: {"published_id": payload["draft_id"]},
    )
    handler = registry.worker_handler(
        "publisher", "publish",
        approval_resolver=lambda skill, action, payload: (
            skill == "publisher" and action == "publish"
            and payload.get("approval_id") == "verified-approval"
        ),
    )
    result = handler({"draft_id": "d1", "approval_id": "verified-approval"})
    assert result["output"] == {"published_id": "d1"}


def test_worker_adapter_fails_closed_without_approval_resolver():
    registry = SkillRegistry()
    registry.register(
        Skill("publisher", "Publish", "Publish approved content",
              (Action.PUBLISH.value,), (Action.PUBLISH.value,)),
        lambda payload: {"published": True},
    )
    with pytest.raises(PermissionError, match="approval required"):
        registry.worker_handler("publisher", "publish")({"draft_id": "d1"})
