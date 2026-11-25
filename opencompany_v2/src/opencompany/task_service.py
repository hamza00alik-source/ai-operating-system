"""Task service enforcing lifecycle rules and recording events."""
import json
from opencompany.domain import Task,TaskStatus,CompanyEvent,utc_now
from opencompany.lifecycle import transition
class TaskService:
 def __init__(self,store):self.store=store
 def create(self,title,objective,department="general",business_id="company"):
  task=Task(title=title,objective=objective,department=department,business_id=business_id)
  self.store.save_task(task);self.store.append_event(CompanyEvent("task_created","owner","task",str(task.id),{"title":title,"department":department}));return task
 def move(self,task_id,target:TaskStatus,actor="system"):
  # Serialize the read/validate/write sequence and keep the state change plus
  # its audit event in one SQLite transaction.
  with self.store.lock:
   self.store.db.execute("BEGIN IMMEDIATE")
   try:
    row=self.store.db.execute("SELECT payload FROM tasks WHERE id=?",(str(task_id),)).fetchone()
    if row is None:raise KeyError("task not found")
    found=json.loads(row["payload"])
    current=TaskStatus(found["status"]);transition(current,target)
    found["status"]=target.value;found["updated_at"]=utc_now()
    found["attempts"]=found.get("attempts",0)+(1 if target==TaskStatus.RUNNING else 0)
    self.store.db.execute("UPDATE tasks SET payload=? WHERE id=?",(json.dumps(found,sort_keys=True),str(task_id)))
    self.store.append_event(CompanyEvent("task_state_changed",actor,"task",str(task_id),{"from":current.value,"to":target.value}))
    return found
   except BaseException:
    if self.store.db.in_transaction:self.store.db.rollback()
    raise

 def assign_to_agent(self,task_id,agent_id,skill_key,actor="ceo"):
  """Assign a READY task to an agent with an explicit persisted skill."""
  task=next((x for x in self.store.list_tasks() if x["id"]==str(task_id)),None)
  if task is None:raise KeyError("task not found")
  if task["status"]!=TaskStatus.READY.value:raise ValueError("task must be READY before assignment")
  profile=self.store.get_agent_profile(agent_id)
  if profile is None:raise KeyError("agent profile not found")
  assignments=self.store.list_skill_assignments(agent_id)
  assignment=next((x for x in assignments if x["skill_key"]==skill_key),None)
  if assignment is None:raise ValueError("skill must be explicitly assigned to agent")
  task["assigned_agent_id"]=agent_id
  task["assigned_skill_key"]=skill_key
  task["assigned_skill_version"]=assignment["skill_version"]
  task["updated_at"]=utc_now()
  with self.store.lock:
   self.store.db.execute("UPDATE tasks SET payload=? WHERE id=?",(json.dumps(task,sort_keys=True),str(task_id)))
   self.store.db.commit()
  self.store.append_event(CompanyEvent("task_assigned",actor,"task",str(task_id),{"agent_id":agent_id,"skill_key":skill_key,"skill_version":assignment["skill_version"]}))
  return task


 def enqueue_assigned(self,task_id,queue,payload=None,max_attempts=3,actor="ceo"):
  """Queue only a READY task with a persisted agent and skill assignment."""
  task=next((x for x in self.store.list_tasks() if x["id"]==str(task_id)),None)
  if task is None:raise KeyError("task not found")
  if task["status"]!=TaskStatus.READY.value:raise ValueError("task must be READY before enqueue")
  agent_id=task.get("assigned_agent_id")
  skill_key=task.get("assigned_skill_key")
  skill_version=task.get("assigned_skill_version")
  if not agent_id or not skill_key or not skill_version:
   raise ValueError("task must have an explicit agent and skill assignment")
  # Revalidate assignment at enqueue time; unassignment revokes future dispatch.
  assignment=next((x for x in self.store.list_skill_assignments(agent_id) if x["skill_key"]==skill_key and x["skill_version"]==skill_version),None)
  if assignment is None:raise ValueError("agent skill assignment is no longer active")
  job_payload=dict(payload or {})
  reserved={"task_id":str(task_id),"agent_id":agent_id,"skill_key":skill_key,"skill_version":skill_version}
  if any(key in job_payload and job_payload[key]!=value for key,value in reserved.items()):
   raise ValueError("payload cannot override assignment metadata")
  job_payload.update(reserved)
  job_id=queue.enqueue(str(task_id),job_payload,max_attempts=max_attempts)
  self.store.append_event(CompanyEvent("task_enqueued",actor,"task",str(task_id),{"job_id":job_id,"agent_id":agent_id,"skill_key":skill_key,"skill_version":skill_version}))
  return job_id


 def record_progress(self,task_id,agent_id,job_id,progress,actor="agent"):
  """Persist bounded, non-sensitive execution progress for owner visibility."""
  if not isinstance(progress,str) or not progress.strip() or len(progress)>2000:
   raise ValueError("progress must be a non-empty string up to 2000 characters")
  task=next((x for x in self.store.list_tasks() if x["id"]==str(task_id)),None)
  if task is None:raise KeyError("task not found")
  if task.get("assigned_agent_id")!=agent_id:raise PermissionError("agent is not assigned to task")
  if task["status"]!=TaskStatus.RUNNING.value:raise ValueError("task must be RUNNING to record progress")
  entries=task.get("execution_progress",[])
  entries.append({"agent_id":agent_id,"job_id":job_id,"message":progress,"at":utc_now()})
  task["execution_progress"]=entries[-100:]
  task["updated_at"]=utc_now()
  with self.store.lock:
   self.store.db.execute("UPDATE tasks SET payload=? WHERE id=?",(json.dumps(task,sort_keys=True),str(task_id)))
   self.store.db.commit()
  self.store.append_event(CompanyEvent("agent_execution_progress",actor,"task",str(task_id),{"job_id":job_id,"message":progress[:500]}))
  return task

 def record_result(self,task_id,agent_id,job_id,result,actor="agent"):
  """Persist a completed deliverable without asserting commercial verification."""
  task=next((x for x in self.store.list_tasks() if x["id"]==str(task_id)),None)
  if task is None:raise KeyError("task not found")
  if task.get("assigned_agent_id")!=agent_id:raise PermissionError("agent is not assigned to task")
  if task["status"]!=TaskStatus.RUNNING.value:raise ValueError("task must be RUNNING to accept a result")
  if not isinstance(result,dict) or result.get("status") not in {"completed","failed","blocked","approval_required"}:
   raise ValueError("result status is not recognized")
  task["execution_result"]=dict(result)
  task["result_recorded_at"]=utc_now()
  task["updated_at"]=utc_now()
  with self.store.lock:
   self.store.db.execute("UPDATE tasks SET payload=? WHERE id=?",(json.dumps(task,sort_keys=True),str(task_id)))
   self.store.db.commit()
  self.store.append_event(CompanyEvent("agent_result_recorded",actor,"task",str(task_id),{"job_id":job_id,"artifact_count":len(result.get("artifacts",[]))}))
  return task


 def review_result(self,task_id,decision,reviewer,notes=""):
  """CEO review gate: accept a completed deliverable or send it back."""
  reviewer_profile=self.store.get_agent_profile(reviewer) if isinstance(reviewer,str) else None
  if reviewer_profile is None or reviewer_profile.role_key.strip().lower()!="ceo":
   raise PermissionError("reviewer must be a registered CEO agent profile")
  if decision not in {"accept","revise"}:
   raise ValueError("decision must be accept or revise")
  if not isinstance(notes,str) or len(notes)>2000:
   raise ValueError("review notes must be text up to 2000 characters")
  task=next((x for x in self.store.list_tasks() if x["id"]==str(task_id)),None)
  if task is None:raise KeyError("task not found")
  current=TaskStatus(task["status"])
  if decision=="accept":
   if current!=TaskStatus.COMPLETED:
    raise ValueError("only COMPLETED tasks can be accepted")
   updated=self.move(task_id,TaskStatus.VERIFIED,actor=reviewer)
  else:
   if current not in {TaskStatus.COMPLETED,TaskStatus.FAILED,TaskStatus.BLOCKED}:
    raise ValueError("task is not eligible for revision")
   updated=self.move(task_id,TaskStatus.READY,actor=reviewer)
   updated["review_notes"]=notes
   with self.store.lock:
    self.store.db.execute("UPDATE tasks SET payload=? WHERE id=?",(json.dumps(updated,sort_keys=True),str(task_id)))
    self.store.db.commit()
  self.store.append_event(CompanyEvent("ceo_result_reviewed",reviewer,"task",str(task_id),{"decision":decision,"notes":notes[:500]}))
  return updated

 def reassign_task(self,task_id,agent_id,skill_key,actor="ceo"):
  """Reassign only a READY task, preserving explicit skill checks."""
  task=next((x for x in self.store.list_tasks() if x["id"]==str(task_id)),None)
  if task is None:raise KeyError("task not found")
  if task["status"]!=TaskStatus.READY.value:
   raise ValueError("task must be READY before reassignment")
  previous=task.get("assigned_agent_id")
  updated=self.assign_to_agent(task_id,agent_id,skill_key,actor=actor)
  self.store.append_event(CompanyEvent("task_reassigned",actor,"task",str(task_id),{"previous_agent_id":previous,"new_agent_id":agent_id,"skill_key":skill_key}))
  return updated
