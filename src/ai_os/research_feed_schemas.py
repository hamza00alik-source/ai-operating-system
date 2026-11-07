"""Schemas for free release-feed research."""
from pydantic import BaseModel, Field, field_validator


class FeedResearchIn(BaseModel):
    query: str = Field(min_length=3, max_length=500)
    category: str = Field(default="technology_research", min_length=1, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=20)
    max_per_feed: int = Field(default=5, ge=1, le=5)

    @field_validator("query", "category")
    @classmethod
    def reject_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value.strip()
