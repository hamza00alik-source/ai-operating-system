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


def test_assigned_task_dispatch_is_agent_scoped_and_audited(tmp_path):
 from opencompany.agent import AgentProfile
 from opencompany.domain import TaskStatus
 from opencompany.queue import ExecutionQueue
 from opencompany.skills import Skill
 from opencompany.store import Store
 from opencompany.task_service import TaskService
 store=Store(str(tmp_path/"dispatch.sqlite"))
 service=TaskService(store)
 store.save_agent_profile(AgentProfile("researcher","Collect buyer evidence",("research",),agent_id="agent-a").validate())
 skill=Skill("buyer_scan","Find buyer evidence","Search public sources",("research",),(),1,("research",)).validate()
 store.assign_skill("agent-a",skill)
 task=service.create("Research buyers","Find evidence",department="research")
 service.move(task.id,TaskStatus.READY)
 service.assign_to_agent(task.id,"agent-a","buyer_scan")
 queue=ExecutionQueue(store.db,store.lock)
 job_id=service.enqueue_assigned(task.id,queue,{"objective":"Find public evidence"})
 job=queue.get(job_id)
 assert job["state"]=="queued"
 assert __import__("json").loads(job["payload"])=={
  "agent_id":"agent-a","objective":"Find public evidence","skill_key":"buyer_scan",
  "skill_version":1,"task_id":str(task.id)}
 assert queue.claim("agent-b",agent_id="agent-b") is None
 assert queue.claim("unscoped-worker") is None
 claimed=queue.claim("worker-a",agent_id="agent-a")
 assert claimed["id"]==job_id
 assert claimed["lease_owner"]=="worker-a"
 assert queue.complete(job_id,"worker-a",{"summary":"Evidence collected"})
 assert queue.get(job_id)["state"]=="completed"
 assert store.verify_event_chain()
 store.close()


def test_dispatch_requires_live_assignment_and_cannot_override_identity(tmp_path):
 from opencompany.agent import AgentProfile
 from opencompany.domain import TaskStatus
 from opencompany.queue import ExecutionQueue
 from opencompany.skills import Skill
 from opencompany.store import Store
 from opencompany.task_service import TaskService
 store=Store(str(tmp_path/"dispatch-guard.sqlite"))
 service=TaskService(store)
 store.save_agent_profile(AgentProfile("researcher","Collect evidence",("research",),agent_id="agent-a").validate())
 skill=Skill("scan","Scan","Search",("research",),(),1,("research",)).validate()
 store.assign_skill("agent-a",skill)
 task=service.create("Scan market","Find evidence")
 service.move(task.id,TaskStatus.READY)
 service.assign_to_agent(task.id,"agent-a","scan")
 queue=ExecutionQueue(store.db,store.lock)
 with pytest.raises(ValueError,match="override"):
  service.enqueue_assigned(task.id,queue,{"agent_id":"agent-b"})
 assert queue.list()==[]
 store.unassign_skill("agent-a","scan")
 with pytest.raises(ValueError,match="no longer active"):
  service.enqueue_assigned(task.id,queue)
 assert queue.list()==[]
 store.close()


def test_agent_worker_executes_only_registered_assigned_skill(tmp_path):
 from opencompany.agent import AgentProfile
 from opencompany.domain import TaskStatus
 from opencompany.queue import ExecutionQueue
 from opencompany.skills import Skill, SkillRegistry
 from opencompany.store import Store
 from opencompany.task_service import TaskService
 from opencompany.worker import AgentWorker
 store=Store(str(tmp_path/"agent-worker.sqlite"))
 service=TaskService(store)
 profile=AgentProfile("researcher","Collect buyer evidence",("research",),agent_id="worker-agent").validate()
 store.save_agent_profile(profile)
 skill=Skill("buyer_scan","Find buyer evidence","Search public sources",("research",),(),1,("research",)).validate()
 store.assign_skill("worker-agent",skill)
 registry=SkillRegistry()
 registry.register(skill,lambda payload: {
  "status":"completed","summary":"Found three relevant buyer signals",
  "artifacts":["evidence-1","evidence-2"],"steps_used":2,"progress":["Collected public signals","Compared buyer evidence"]})
 task=service.create("Research buyers","Find buyer demand")
 service.move(task.id,TaskStatus.READY)
 service.assign_to_agent(task.id,"worker-agent","buyer_scan")
 queue=ExecutionQueue(store.db,store.lock)
 job_id=service.enqueue_assigned(task.id,queue,{"objective":"Find buyer signals"})
 worker=AgentWorker("worker-agent",store,queue,registry,{"buyer_scan":"research"},task_service=service)
 report=worker.run_once()
 assert report["status"]=="completed"
 assert report["steps_used"]==2
 assert report["artifacts"]==["evidence-1","evidence-2"]
 assert queue.get(job_id)["state"]=="completed"
 saved=next(x for x in store.list_tasks() if x["id"]==str(task.id))
 assert saved["status"]=="completed"
 assert saved["execution_result"]["summary"]=="Found three relevant buyer signals"
 assert [x["message"] for x in saved["execution_progress"]]==["Collected public signals","Compared buyer evidence"]
 assert store.verify_event_chain()
 event_kinds=[__import__("json").loads(x["payload"])["kind"] for x in store.db.execute("SELECT payload FROM events ORDER BY seq")]
 assert "agent_execution_started" in event_kinds
 assert "agent_execution_result" in event_kinds
 store.close()


def test_agent_worker_fails_closed_when_skill_assignment_revoked(tmp_path):
 from opencompany.agent import AgentProfile
 from opencompany.domain import TaskStatus
 from opencompany.queue import ExecutionQueue
 from opencompany.skills import Skill, SkillRegistry
 from opencompany.store import Store
 from opencompany.task_service import TaskService
 from opencompany.worker import AgentWorker
 store=Store(str(tmp_path/"agent-worker-revoked.sqlite"))
 service=TaskService(store)
 store.save_agent_profile(AgentProfile("researcher","Collect evidence",("research",),agent_id="worker-agent").validate())
 skill=Skill("scan","Scan","Search",("research",),(),1,("research",)).validate()
 store.assign_skill("worker-agent",skill)
 registry=SkillRegistry()
 registry.register(skill,lambda payload: {"status":"completed","summary":"Should not run","steps_used":1})
 task=service.create("Scan market","Find evidence")
 service.move(task.id,TaskStatus.READY)
 service.assign_to_agent(task.id,"worker-agent","scan")
 queue=ExecutionQueue(store.db,store.lock)
 service.enqueue_assigned(task.id,queue)
 store.unassign_skill("worker-agent","scan")
 worker=AgentWorker("worker-agent",store,queue,registry,{"scan":"research"})
 with pytest.raises(PermissionError,match="no longer active"):
  worker.run_once()
 assert queue.list()[0]["state"]=="queued"
 store.close()


def test_ceo_can_accept_or_return_completed_deliverable(tmp_path):
 from opencompany.domain import TaskStatus
 from opencompany.store import Store
 from opencompany.task_service import TaskService
 store=Store(str(tmp_path/"ceo-review.sqlite"))
 service=TaskService(store)
 from opencompany.agent import AgentProfile
 store.save_agent_profile(AgentProfile("ceo","Review agent deliverables",("review",),agent_id="ceo-agent").validate())
 store.save_agent_profile(AgentProfile("researcher","Research",("research",),agent_id="research-agent").validate())
 task=service.create("Prepare buyer report","Research demand")
 service.move(task.id,TaskStatus.READY)
 service.move(task.id,TaskStatus.RUNNING)
 service.move(task.id,TaskStatus.COMPLETED,actor="research-agent")
 with pytest.raises(PermissionError,match="only the CEO"):
  service.review_result(task.id,"accept",reviewer="research-agent")
 accepted=service.review_result(task.id,"accept",reviewer="ceo-agent",notes="Evidence checked")
 assert accepted["status"]=="verified"
 task2=service.create("Prepare product brief","Draft product brief")
 service.move(task2.id,TaskStatus.READY)
 service.move(task2.id,TaskStatus.RUNNING)
 service.move(task2.id,TaskStatus.COMPLETED,actor="writer-agent")
 revised=service.review_result(task2.id,"revise",reviewer="ceo-agent",notes="Add source citations")
 assert revised["status"]=="ready"
 assert revised["review_notes"]=="Add source citations"
 assert store.verify_event_chain()
 store.close()


def test_ceo_reassignment_requires_ready_task_and_valid_agent_skill(tmp_path):
 from opencompany.agent import AgentProfile
 from opencompany.domain import TaskStatus
 from opencompany.skills import Skill
 from opencompany.store import Store
 from opencompany.task_service import TaskService
 store=Store(str(tmp_path/"reassign.sqlite"))
 service=TaskService(store)
 for agent in ("agent-old","agent-new"):
  store.save_agent_profile(AgentProfile("researcher","Research",("research",),agent_id=agent).validate())
 skill=Skill("scan","Scan","Search public sources",("research",),(),1,("research",)).validate()
 store.assign_skill("agent-old",skill)
 store.assign_skill("agent-new",skill)
 task=service.create("Scan buyers","Find demand")
 service.move(task.id,TaskStatus.READY)
 service.assign_to_agent(task.id,"agent-old","scan")
 moved=service.reassign_task(task.id,"agent-new","scan")
 assert moved["assigned_agent_id"]=="agent-new"
 with pytest.raises(ValueError,match="READY"):
  service.move(task.id,TaskStatus.RUNNING)
  service.reassign_task(task.id,"agent-old","scan")
 assert store.verify_event_chain()
 store.close()


def test_sale_evidence_is_persisted_without_inventing_received_revenue(tmp_path):
 from opencompany.revenue import SaleEvidence
 from opencompany.store import Store
 store=Store(str(tmp_path/"sales.sqlite"))
 sale=SaleEvidence("ORDER-100","Marketplace",25.0,"USD","platform order receipt")
 saved=store.record_sale_evidence(sale)
 assert saved["received"] is False
 assert store.list_sale_evidence(received=True)==[]
 assert len(store.list_sale_evidence(received=False))==1
 # Re-submitting the same order is idempotent, not a second sale.
 again=store.record_sale_evidence(SaleEvidence("ORDER-100","Marketplace",25.0,"USD","platform order receipt"))
 assert again["id"]==saved["id"]
 with pytest.raises(PermissionError,match="Owner approval"):
  store.confirm_sale_received(saved["id"],actor="ceo",payment_reference="TX-1")
 with pytest.raises(ValueError,match="payment reference"):
  store.confirm_sale_received(saved["id"],actor="ceo",owner_approved=True)
 received=store.confirm_sale_received(saved["id"],actor="owner",owner_approved=True,payment_reference="TX-100")
 assert received["received"] is True
 assert received["payment_reference"]=="TX-100"
 assert len(store.list_sale_evidence(received=True))==1
 with pytest.raises(ValueError,match="already confirmed"):
  store.confirm_sale_received(saved["id"],actor="owner",owner_approved=True,payment_reference="TX-100")
 store.close()


def test_sale_evidence_rejects_conflicting_duplicate_order(tmp_path):
 from opencompany.revenue import SaleEvidence
 from opencompany.store import Store
 store=Store(str(tmp_path/"sales-conflict.sqlite"))
 store.record_sale_evidence(SaleEvidence("ORDER-101","Marketplace",25.0,"USD","receipt-a"))
 with pytest.raises(ValueError,match="different evidence"):
  store.record_sale_evidence(SaleEvidence("ORDER-101","Marketplace",30.0,"USD","receipt-b"))
 store.close()


def test_revenue_totals_are_separated_and_only_count_confirmed_receipts(tmp_path):
 from opencompany.revenue import SaleEvidence
 from opencompany.store import Store
 path=str(tmp_path/"revenue-lines.sqlite")
 store=Store(path)
 agency=store.record_sale_evidence(SaleEvidence(
  "AG-1","AgencyPlatform",100.0,"USD","order receipt",
  business_line="physical_agency"))
 own=store.record_sale_evidence(SaleEvidence(
  "OWN-1","OwnStore",50.0,"USD","order receipt",
  business_line="own_physical_brand"))
 digital=store.record_sale_evidence(SaleEvidence(
  "DIG-1","DigitalStore",20.0,"EUR","order receipt",
  business_line="digital_products"))
 unclassified=store.record_sale_evidence(SaleEvidence(
  "UNK-1","OtherStore",999.0,"USD","order receipt"))
 store.confirm_sale_received(agency["id"],actor="owner",owner_approved=True,payment_reference="PAY-AG")
 store.confirm_sale_received(digital["id"],actor="owner",owner_approved=True,payment_reference="PAY-DIG")
 assert store.revenue_totals(business_line="physical_agency",currency="USD")["gross_received"]==100.0
 assert store.revenue_totals(business_line="own_physical_brand",currency="USD")["gross_received"]==0
 assert store.revenue_totals(business_line="digital_products",currency="EUR")["gross_received"]==20.0
 assert store.revenue_totals(business_line="physical_agency",currency="USD")["confirmed_receipts_count"]==1
 assert store.revenue_totals(business_line="physical_agency",currency="USD")["net_profit"] is None
 assert store.list_sale_evidence(business_line="unclassified")[0]["id"]==unclassified["id"]
 store.close()
 # Evidence and classification survive a database restart.
 reopened=Store(path)
 assert reopened.revenue_totals(business_line="physical_agency",currency="USD")["gross_received"]==100.0
 assert reopened.revenue_totals(business_line="own_physical_brand",currency="USD")["gross_received"]==0
 reopened.close()


def test_sale_evidence_rejects_unknown_business_line():
 from opencompany.revenue import SaleEvidence
 with pytest.raises(ValueError,match="business line"):
  SaleEvidence("ORDER-X","Store",10.0,"USD","receipt",business_line="mixed")
