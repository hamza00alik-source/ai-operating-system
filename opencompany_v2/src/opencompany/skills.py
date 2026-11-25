"""Versioned executable skill contracts with fail-closed action permissions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable
from opencompany.permissions import Action, permission_decision

@dataclass(frozen=True)
class Skill:
    key: str
    purpose: str
    procedure: str
    allowed_actions: tuple[str, ...] = ()
    approval_actions: tuple[str, ...] = ()
    version: int = 1
    required_capabilities: tuple[str, ...] = ()

    def validate(self):
        if not self.key or not self.purpose or not self.procedure:
            raise ValueError("Skill must have key, purpose and procedure.")
        if self.version < 1:
            raise ValueError("Skill version must be a positive integer.")
        if len(set(self.allowed_actions)) != len(self.allowed_actions):
            raise ValueError("Skill allowed actions must be unique.")
        if set(self.approval_actions) - set(self.allowed_actions):
            raise ValueError("Approval actions must be included in allowed actions.")
        if any(not isinstance(value, str) or not value.strip()
               for value in self.required_capabilities):
            raise ValueError("Required capabilities must be non-empty strings.")
        if len(set(self.required_capabilities)) != len(self.required_capabilities):
            raise ValueError("Required capabilities must be unique.")
        for action in self.allowed_actions:
            try:
                Action(action)
            except ValueError as exc:
                raise ValueError(f"Unknown skill action: {action}") from exc
        return self

@dataclass(frozen=True)
class SkillResult:
    skill_key: str
    skill_version: int
    action: str
    output: Any

class SkillRegistry:
    """In-process registry; only registered handlers can execute skill work."""
    def __init__(self):
        self._skills: dict[str, tuple[Skill, Callable[[Any], Any]]] = {}

    def register(self, skill: Skill, handler: Callable[[Any], Any]) -> None:
        skill.validate()
        if not callable(handler):
            raise TypeError("Skill handler must be callable.")
        if skill.key in self._skills:
            raise ValueError(f"Skill already registered: {skill.key}")
        self._skills[skill.key] = (skill, handler)

    @staticmethod
    def _public_contract(skill: Skill) -> dict[str, Any]:
        return {
            "key": skill.key,
            "purpose": skill.purpose,
            "version": skill.version,
            "allowed_actions": list(skill.allowed_actions),
            "approval_actions": list(skill.approval_actions),
            "required_capabilities": list(skill.required_capabilities),
        }

    def list(self) -> list[dict[str, Any]]:
        """Return a stable, read-only catalog view without exposing handlers."""
        return [
            self._public_contract(skill)
            for skill, _handler in sorted(
                self._skills.values(), key=lambda item: item[0].key
            )
        ]

    def eligible_for(self, agent: Any) -> list[dict[str, Any]]:
        """List contracts whose declared capability requirements the agent meets.

        This is discovery only; it does not assign a skill or grant permission
        to execute any action.
        """
        validator = getattr(agent, "validate", None)
        if callable(validator):
            validator()
        capabilities = getattr(agent, "capabilities", None)
        if (not isinstance(capabilities, (tuple, list, set, frozenset))
                or any(not isinstance(value, str) or not value.strip()
                       for value in capabilities)):
            raise TypeError("Agent must expose a collection of non-empty capability strings.")
        available = set(capabilities)
        return [
            self._public_contract(skill)
            for skill, _handler in sorted(
                self._skills.values(), key=lambda item: item[0].key
            )
            if set(skill.required_capabilities).issubset(available)
        ]

    def execute(self, skill_key: str, action: str, payload: Any,
                *, owner_approved: bool = False) -> SkillResult:
        if skill_key not in self._skills:
            raise KeyError(f"Unknown skill: {skill_key}")
        skill, handler = self._skills[skill_key]
        if action not in skill.allowed_actions:
            raise PermissionError(f"Action is outside skill scope: {action}")
        decision = permission_decision(Action(action), owner_approved=owner_approved)
        if decision != "allowed" or (
            action in skill.approval_actions and not owner_approved
        ):
            raise PermissionError(f"Owner approval required for action: {action}")
        output = handler(payload)
        return SkillResult(skill.key, skill.version, action, output)

    def worker_handler(
        self,
        skill_key: str,
        action: str,
        *,
        approval_resolver: Callable[[str, str, dict], bool] | None = None,
    ) -> Callable[[dict], dict]:
        """Create a Worker-compatible handler.

        Approval is resolved by trusted server-side code, never by job payload
        fields. Without a resolver, sensitive actions remain blocked.
        """
        def run(payload: dict) -> dict:
            approved = bool(
                approval_resolver(skill_key, action, payload)
                if approval_resolver is not None else False
            )
            result = self.execute(
                skill_key, action, payload, owner_approved=approved
            )
            if not isinstance(result.output, dict):
                raise TypeError("Worker skill handlers must return a dictionary.")
            return {
                "skill_key": result.skill_key,
                "skill_version": result.skill_version,
                "action": result.action,
                "output": result.output,
            }
        return run
