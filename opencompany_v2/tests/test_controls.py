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
