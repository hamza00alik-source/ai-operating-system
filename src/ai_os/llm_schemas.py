"""Request and response models for LLM connectivity checks."""
from pydantic import BaseModel, Field


class LLMTestRequest(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    prompt: str = Field(default="Reply with exactly: AIOS connection test passed.", min_length=1, max_length=1000)
