"""Validated input models for source-attributed company knowledge."""
from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, Field, field_validator


class KnowledgeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    category: str = Field(min_length=1, max_length=80)
    source_url: AnyHttpUrl
    source_title: str = Field(min_length=1, max_length=200)
    source_published_at: datetime | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("title", "content", "category", "source_title")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text fields must not be blank.")
        return value.strip()

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized = []
        for value in values:
            if not isinstance(value, str) or not value.strip() or len(value) > 60:
                raise ValueError("Each tag must be non-empty and at most 60 characters.")
            normalized.append(value.strip().lower())
        if len(normalized) != len(set(normalized)):
            raise ValueError("Tags must be unique.")
        return normalized


class KnowledgeReview(BaseModel):
    decision: Literal["accepted", "rejected"]
    note: str = Field(default="", max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return value.strip()
