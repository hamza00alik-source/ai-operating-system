"""Request/response schemas for the agent control-plane registry."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict


class AgentEnableUpdate(BaseModel):
    enabled: bool


class EndpointCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    protocol: Literal["internal", "mcp", "a2a", "openai_compatible"]
    base_url: str | None = Field(default=None, max_length=500)
    credential_ref: str | None = Field(default=None, max_length=160)
    metadata: dict = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("metadata")
    @classmethod
    def limit_metadata(cls, value: dict) -> dict:
        if len(str(value)) > 4000:
            raise ValueError("metadata is too large")
        forbidden_parts = ("secret", "token", "password", "api_key", "apikey", "authorization")
        def inspect(item):
            if isinstance(item, dict):
                for key, child in item.items():
                    normalized = str(key).lower().replace("-", "_")
                    if any(part in normalized for part in forbidden_parts):
                        raise ValueError("metadata must not contain credentials or secret material")
                    inspect(child)
            elif isinstance(item, list):
                for child in item:
                    inspect(child)
        inspect(value)
        return value


class AgentRegistryList(BaseModel):
    model_config = ConfigDict(extra="allow")
