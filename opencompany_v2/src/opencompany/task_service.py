"""Task service enforcing lifecycle rules and recording events."""
from dataclasses import replace
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
