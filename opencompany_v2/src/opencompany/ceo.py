"""CEO planning logic: prioritization and bounded task decomposition."""
from dataclasses import dataclass
@dataclass(frozen=True)
class Plan:
 goal:str
 tasks:tuple[dict,...]
 risks:tuple[str,...]
 def validate(self):
  if not self.goal.strip():raise ValueError("Plan needs a goal")
  if not 1<=len(self.tasks)<=30:raise ValueError("Plans must contain 1..30 tasks")
  for task in self.tasks:
   if not task.get("title") or not task.get("objective"):raise ValueError("Every task needs a title and objective")
  return self
class CEOPlanner:
 def rank_opportunities(self,scored_items):
  return sorted(scored_items,key=lambda item:(item["score"],item.get("evidence_count",0)),reverse=True)
 def draft_plan(self,goal,tasks,risks=()):return Plan(goal,tuple(tasks),tuple(risks)).validate()
