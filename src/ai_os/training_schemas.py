"""Owner-reviewed training corpus API contracts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TrainingExampleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_family: str = Field(min_length=2, max_length=80)
    system_prompt: str = Field(min_length=1, max_length=8000)
    user_input: str = Field(min_length=1, max_length=12000)
    ideal_response: str = Field(min_length=1, max_length=12000)
    source_refs: list[str] = Field(default_factory=list, max_length=20)
    rights_confirmed: bool
    privacy_reviewed: bool

    @field_validator("source_refs")
    @classmethod
    def valid_source_refs(cls, values: list[str]) -> list[str]:
        from urllib.parse import urlparse
        normalized = []
        for value in values:
            parsed = urlparse(value)
            if parsed.scheme != "https" or not parsed.netloc or len(value) > 2048:
                raise ValueError("Training source references must be HTTPS URLs.")
            normalized.append(value)
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def require_owner_attestations(self):
        if not self.task_family.strip():
            raise ValueError("Task family must not be blank.")
        if not self.system_prompt.strip() or not self.user_input.strip() or not self.ideal_response.strip():
            raise ValueError("Training prompt, input, and ideal response must not be blank.")
        if not self.rights_confirmed or not self.privacy_reviewed:
            raise ValueError("Rights and privacy review must both be confirmed before a training candidate is stored.")
        return self


class TrainingExampleReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["accepted", "rejected"]
    note: str = Field(default="", max_length=2000)


class TrainingDatasetExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=500, ge=1, le=1000)
