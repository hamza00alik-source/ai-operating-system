import pytest
from opencompany.domain import TaskStatus
from opencompany.lifecycle import transition
from opencompany.permissions import Action, permission_decision
from opencompany.revenue import SaleEvidence
from opencompany.skills import Skill

def test_task_state_machine():
 assert transition(TaskStatus.DISCOVERED,TaskStatus.READY)==TaskStatus.READY
 with pytest.raises(ValueError): transition(TaskStatus.DISCOVERED,TaskStatus.VERIFIED)
def test_sensitive_actions_need_approval():
 assert permission_decision(Action.PUBLISH)=="approval_required"
 assert permission_decision(Action.PUBLISH,owner_approved=True)=="allowed"
 assert permission_decision(Action.RESEARCH)=="allowed"
def test_sale_requires_evidence():
 with pytest.raises(ValueError): SaleEvidence("order","platform",10,"USD","")

def test_skill_action_scope():
 Skill("market_scan","Find public evidence","Search and summarize",("research",),()).validate()
 with pytest.raises(ValueError): Skill("unsafe","x","y",("read",),("publish",)).validate()


def test_agent_profile_validates_capabilities_and_budget():
 from opencompany.agent import AgentProfile
 profile=AgentProfile("researcher","Find public buyer evidence",("research","web_read")).validate()
 assert profile.can("research")
 assert not profile.can("publish")
 with pytest.raises(ValueError,match="unique"):
  AgentProfile("researcher","Find evidence",("research","research")).validate()
 with pytest.raises(ValueError,match="non-empty strings"):
  AgentProfile("researcher","Find evidence",("research","")).validate()
 with pytest.raises(ValueError,match="integer"):
  AgentProfile("researcher","Find evidence",("research",),max_steps=True).validate()


def test_agent_profile_rejects_capability_prohibition_conflict():
 from opencompany.agent import AgentProfile
 with pytest.raises(ValueError,match="conflicts"):
  AgentProfile("publisher","Prepare drafts",("draft","publish"),("publish",)).validate()


def test_agent_result_enforces_bounded_integer_steps_and_artifacts():
 from opencompany.agent import AgentResult
 assert AgentResult("completed","Draft ready",("draft-1",),2).validate(3).steps_used==2
 with pytest.raises(ValueError,match="step budget"):
  AgentResult("completed","Done",(),True).validate(3)
 with pytest.raises(ValueError,match="artifacts"):
  AgentResult("completed","Done",("",),1).validate(3)
