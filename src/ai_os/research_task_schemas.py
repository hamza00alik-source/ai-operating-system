"""Request schemas for CEO research task proposal drafting and review."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator


class ResearchTaskProposalReview(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=1000)

    @field_validator("note")
    @classmethod
    def normalize_note(cls, value: str) -> str:
        return value.strip()
