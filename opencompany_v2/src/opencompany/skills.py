"""First-party skill contract: descriptive, versioned and permission-scoped."""
from dataclasses import dataclass
@dataclass(frozen=True)
class Skill:
    key:str
    purpose:str
    procedure:str
    allowed_actions:tuple[str,...]=()
    approval_actions:tuple[str,...]=()
    version:int=1
    def validate(self):
        if not self.key or not self.purpose or not self.procedure: raise ValueError("Skill must have key, purpose and procedure.")
        if set(self.approval_actions)-set(self.allowed_actions): raise ValueError("Approval actions must be included in allowed actions.")
        return self
