"""Request/response schemas for the agent control-plane registry."""
from typing import Literal
import re
from pydantic import BaseModel, Field, field_validator, ConfigDict


class AgentEnableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class EndpointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    protocol: Literal["internal", "mcp", "a2a", "openai_compatible"]
    base_url: str | None = Field(default=None, max_length=500)
    credential_ref: str | None = Field(default=None, max_length=160)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("credential_ref")
    @classmethod
    def validate_credential_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not (value.startswith("env:") or value.startswith("secret://") or re.fullmatch(r"vault:[0-9a-fA-F-]{36}", value)):
            raise ValueError("credential_ref must be an env:NAME, secret://, or vault:UUID reference, never a credential value")
        if len(value) > 160 or any(ch.isspace() for ch in value):
            raise ValueError("credential_ref must be a short reference")
        return value

class RuntimeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime_name: str = Field(min_length=1, max_length=100)
    runtime_kind: Literal["worker", "agent"]
    agent_id: str | None = Field(default=None, max_length=120)

    @field_validator("runtime_name")
    @classmethod
    def clean_runtime_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("runtime_name must not be blank")
        return value


class RuntimeHeartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    runtime_id: str = Field(min_length=1, max_length=120)
    status: Literal["starting", "idle", "working", "paused", "stopped", "error"]
    current_job_id: str | None = Field(default=None, max_length=120)


class CapabilityGrantCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str = Field(min_length=1, max_length=120)
    capability: str = Field(min_length=3, max_length=80)
    department_scope: str | None = Field(default=None, max_length=100)

    @field_validator("capability")
    @classmethod
    def clean_capability(cls, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise ValueError("capability must not be blank")
        return value


class BrokerRouteEvaluate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_agent_id: str = Field(min_length=1, max_length=120)
    target_agent_id: str = Field(min_length=1, max_length=120)


class CapabilityEvaluate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: str = Field(min_length=1, max_length=120)
    capability: str = Field(min_length=3, max_length=80)
    department_scope: str | None = Field(default=None, max_length=100)



class EndpointEnableUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
