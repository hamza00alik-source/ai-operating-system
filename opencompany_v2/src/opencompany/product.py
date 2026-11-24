"""Product workflow records; ready-to-publish is distinct from published."""
from dataclasses import dataclass,field
from enum import StrEnum
from uuid import uuid4
from datetime import datetime,timezone
class ProductStage(StrEnum): IDEA="idea";RESEARCHED="researched";DRAFT="draft";QA="qa";READY_FOR_OWNER="ready_for_owner";APPROVED="approved";PUBLISHED="published";ARCHIVED="archived"
@dataclass(frozen=True)
class ProductDraft:
 title:str
 buyer_problem:str
 description:str
 price_minor:int
 currency:str
 files:tuple[str,...]=() qa_checks:tuple[str,...]=() stage:ProductStage=ProductStage.IDEA
 id:str=field(default_factory=lambda:str(uuid4()))
 created_at:str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat())
 def validate_for_owner_review(self):
  if len(self.title.strip())<4:raise ValueError("Product title too short")
  if not self.buyer_problem.strip():raise ValueError("Buyer problem must be stated")
  if not self.description.strip():raise ValueError("Product description is required")
  if self.price_minor<0 or len(self.currency)!=3:raise ValueError("Invalid price or currency")
  if not self.files:raise ValueError("Attach at least one product file")
  if not self.qa_checks or any(not check.strip() for check in self.qa_checks):raise ValueError("QA checks must be recorded")
  return self
