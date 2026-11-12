"""Immutable outputs produced by supervised agent execution."""
from dataclasses import dataclass
from uuid import UUID

@dataclass(frozen=True)
class AgentDeliverable:
    id: UUID
    work_item_id: UUID
    role_key: str
    content: str
    provider: str
    model: str
    cost_usd: float = 0.0
    def __post_init__(self):
        if not isinstance(self.id, UUID) or not isinstance(self.work_item_id, UUID):
            raise ValueError("deliverable and work item IDs must be UUIDs")
        if not all(isinstance(v,str) and v.strip() for v in (self.role_key,self.content,self.provider,self.model)):
            raise ValueError("deliverable fields must be non-empty")
        if self.cost_usd < 0:
            raise ValueError("deliverable cost cannot be negative")
