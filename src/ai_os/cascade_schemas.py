"""Request model for free-first cascading LLM chat."""
from pydantic import BaseModel, Field


class LLMChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=12000)
    system: str | None = Field(default=None, max_length=4000)
    max_tokens: int = Field(default=500, ge=1, le=4000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
