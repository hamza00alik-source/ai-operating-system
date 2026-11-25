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
  items=self.store.list_tasks();found=next((x for x in items if x["id"]==str(task_id)),None)
  if not found:raise KeyError("task not found")
  current=TaskStatus(found["status"]);transition(current,target)
  found["status"]=target.value;found["updated_at"]=utc_now();found["attempts"]=found.get("attempts",0)+(1 if target==TaskStatus.RUNNING else 0)
  self.store.db.execute("UPDATE tasks SET payload=? WHERE id=?",(__import__("json").dumps(found,sort_keys=True),str(task_id)));self.store.db.commit()
  self.store.append_event(CompanyEvent("task_state_changed",actor,"task",str(task_id),{"from":current.value,"to":target.value}));return found

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
