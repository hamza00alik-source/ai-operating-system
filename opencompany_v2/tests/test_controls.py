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


def test_agent_profiles_persist_and_update_explicitly(tmp_path):
 from opencompany.agent import AgentProfile
 from opencompany.store import Store
 store=Store(str(tmp_path/"agents.sqlite"))
 profile=AgentProfile("researcher","Find evidence",("research",),agent_id="agent-1").validate()
 store.save_agent_profile(profile)
 assert store.get_agent_profile("agent-1")==profile
 assert store.list_agent_profiles()==[profile]
 changed=AgentProfile("researcher","Find evidence",("research","web_read"),agent_id="agent-1").validate()
 with pytest.raises(ValueError,match="use update_agent_profile"):
  store.save_agent_profile(changed)
 store.update_agent_profile(changed)
 assert store.get_agent_profile("agent-1")==changed
 with pytest.raises(KeyError,match="not found"):
  store.update_agent_profile(AgentProfile("new","mission",("research",),agent_id="missing"))
 store.close()

def test_agent_skill_assignment_persists_and_checks_capabilities(tmp_path):
 from opencompany.agent import AgentProfile
 from opencompany.skills import Skill
 from opencompany.store import Store
 store=Store(str(tmp_path/"skills.sqlite"))
 profile=AgentProfile("researcher","Collect buyer evidence",("research",),agent_id="research-1").validate()
 store.save_agent_profile(profile)
 skill=Skill("buyer_scan","Find buyer evidence","Search public sources",("research",),(),1,("research",)).validate()
 assignment=store.assign_skill("research-1",skill)
 assert assignment["skill_key"]=="buyer_scan"
 assert store.list_skill_assignments("research-1")[0]["skill_version"]==1
 assert store.assign_skill("research-1",skill)==assignment
 newer=Skill("buyer_scan","Find buyer evidence","Search public sources",("research",),(),2,("research",)).validate()
 with pytest.raises(ValueError,match="another version"):
  store.assign_skill("research-1",newer)
 assert store.unassign_skill("research-1","buyer_scan") is True
 assert store.list_skill_assignments("research-1")==[]
 assert store.unassign_skill("research-1","buyer_scan") is False
 store.close()


def test_agent_skill_assignment_rejects_missing_capability_and_prohibited_actions(tmp_path):
 from opencompany.agent import AgentProfile
 from opencompany.skills import Skill
 from opencompany.store import Store
 store=Store(str(tmp_path/"skills-reject.sqlite"))
 store.save_agent_profile(AgentProfile("writer","Draft content",("draft",),agent_id="writer-1").validate())
 needs_research=Skill("research_skill","Research","Search",("research",),(),1,("research",)).validate()
 with pytest.raises(ValueError,match="lacks required"):
  store.assign_skill("writer-1",needs_research)
 store.save_agent_profile(AgentProfile("guarded","No external contact",("research",),("contact_customer",),agent_id="guarded-1").validate())
 contact_skill=Skill("contact","Contact buyer","Send contact",("contact_customer",),(),1,("research",)).validate()
 with pytest.raises(ValueError,match="prohibited agent actions"):
  store.assign_skill("guarded-1",contact_skill)
 with pytest.raises(KeyError,match="not found"):
  store.assign_skill("missing",needs_research)
 store.close()

def test_ready_task_can_only_be_assigned_with_agent_skill(tmp_path):
 from opencompany.agent import AgentProfile
 from opencompany.domain import TaskStatus
 from opencompany.skills import Skill
 from opencompany.store import Store
 from opencompany.task_service import TaskService
 store=Store(str(tmp_path/"task-assignment.sqlite"))
 service=TaskService(store)
 profile=AgentProfile("researcher","Collect buyer evidence",("research",),agent_id="research-2").validate()
 store.save_agent_profile(profile)
 skill=Skill("buyer_scan","Find buyer evidence","Search public sources",("research",),(),1,("research",)).validate()
 store.assign_skill("research-2",skill)
 task=service.create("Research buyers","Find evidence of demand",department="research")
 with pytest.raises(ValueError,match="READY"):
  service.assign_to_agent(task.id,"research-2","buyer_scan")
 service.move(task.id,TaskStatus.READY)
 assigned=service.assign_to_agent(task.id,"research-2","buyer_scan")
 assert assigned["assigned_agent_id"]=="research-2"
 assert assigned["assigned_skill_key"]=="buyer_scan"
 assert assigned["assigned_skill_version"]==1
 stored=next(x for x in store.list_tasks() if x["id"]==str(task.id))
 assert stored["assigned_agent_id"]=="research-2"
 assert store.verify_event_chain()
 store.close()
