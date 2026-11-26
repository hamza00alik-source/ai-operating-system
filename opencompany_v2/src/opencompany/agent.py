"""First-party agent contract: objectives, capabilities, bounded execution."""
from dataclasses import dataclass, field
from uuid import uuid4


@dataclass(frozen=True)
class AgentProfile:
    role_key: str
    mission: str
    capabilities: tuple[str, ...]
    prohibited_actions: tuple[str, ...] = ()
    max_steps: int = 8
    agent_id: str = field(default_factory=lambda: str(uuid4()))

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    def validate(self):
        if not isinstance(self.role_key, str) or not self.role_key.strip():
            raise ValueError("Agent role is required")
        if not isinstance(self.mission, str) or not self.mission.strip():
            raise ValueError("Agent mission is required")
        if (not isinstance(self.max_steps, int) or isinstance(self.max_steps, bool)
                or not 1 <= self.max_steps <= 100):
            raise ValueError("Execution step budget must be an integer from 1 to 100")
        for label, values in (
            ("Capabilities", self.capabilities),
            ("Prohibited actions", self.prohibited_actions),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"{label} must be a tuple of non-empty strings")
            if len(set(values)) != len(values):
                raise ValueError(f"{label} must be unique")
        if set(self.capabilities) & set(self.prohibited_actions):
            raise ValueError("Capability conflicts with prohibited actions")
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise ValueError("Agent ID is required")
        return self


@dataclass(frozen=True)
class AgentResult:
    status: str
    summary: str
    artifacts: tuple[str, ...] = ()
    steps_used: int = 0

    def validate(self, limit: int):
        if self.status not in {"completed", "failed", "blocked", "approval_required"}:
            raise ValueError("Unknown result status")
        if (not isinstance(self.steps_used, int) or isinstance(self.steps_used, bool)
                or not isinstance(limit, int) or isinstance(limit, bool)
                or not 0 <= self.steps_used <= limit):
            raise ValueError("Agent exceeded its step budget")
        if not isinstance(self.summary, str):
            raise ValueError("Agent result summary must be text")
        if not isinstance(self.artifacts, tuple) or any(
            not isinstance(item, str) or not item.strip() for item in self.artifacts
        ):
            raise ValueError("Agent result artifacts must be non-empty text values")
        return self
