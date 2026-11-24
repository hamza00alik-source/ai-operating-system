"""First-party agent contract: objectives, capabilities, bounded execution."""
from dataclasses import dataclass,field
from uuid import uuid4
@dataclass(frozen=True)
class AgentProfile:
 role_key:str
 mission:str
 capabilities:tuple[str,...]
 prohibited_actions:tuple[str,...]=()
 max_steps:int=8
 agent_id:str=field(default_factory=lambda:str(uuid4()))
 def can(self,capability:str)->bool:return capability in self.capabilities
 def validate(self):
  if not self.role_key or not self.mission:raise ValueError("Agent role and mission required")
  if not 1<=self.max_steps<=100:raise ValueError("Execution step budget must be 1..100")
  if set(self.capabilities)&set(self.prohibited_actions):raise ValueError("Capability conflicts with prohibited actions")
  return self
@dataclass(frozen=True)
class AgentResult:
 status:str
 summary:str
 artifacts:tuple[str,...]=()
 steps_used:int=0
 def validate(self,limit:int):
  if self.status not in {"completed","failed","blocked","approval_required"}:raise ValueError("Unknown result status")
  if not 0<=self.steps_used<=limit:raise ValueError("Agent exceeded its step budget")
  return self
