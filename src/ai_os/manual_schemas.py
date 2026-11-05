"""Schemas for the no-API manual execution workflow."""
from pydantic import BaseModel, Field

class WorkPacketCreate(BaseModel):
    agent_id: str = Field(min_length=1, max_length=120)
    task: str = Field(min_length=1, max_length=8000)
    context: str = Field(default="", max_length=12000)

class WorkPacketOut(BaseModel):
    packet_id: str
    agent: dict[str, str]
    execution_mode: str
    model_invoked: bool
    api_called: bool
    prompt_text: str
    notice: str

class RuntimeStatus(BaseModel):
    mode: str
    agent_profiles_available: bool
    manual_free_chat_available: bool
    model_api_configured: bool
    paid_api_calls_enabled: bool
    autonomous_execution_enabled: bool
    external_actions_enabled: bool
