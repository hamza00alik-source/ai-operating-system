"""Revenue records are evidence-backed and never inferred from agent activity."""
from dataclasses import dataclass,field
from datetime import datetime,timezone
from uuid import uuid4,UUID
@dataclass(frozen=True)
class SaleEvidence:
    order_reference:str
    platform:str
    gross_amount:float
    currency:str
    verified_source:str
    received:bool=False
    business_line:str="unclassified"
    id:UUID=field(default_factory=uuid4)
    recorded_at:str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat())
    def __post_init__(self):
        if not self.order_reference.strip() or not self.platform.strip() or not self.verified_source.strip(): raise ValueError("Sale requires order, platform and evidence source.")
        if self.gross_amount<=0: raise ValueError("Sale amount must be positive.")
        if len(self.currency)!=3: raise ValueError("Currency must be a 3-letter code.")
        if self.business_line not in {"physical_agency","own_physical_brand","digital_products","unclassified"}: raise ValueError("Unknown business line.")
@dataclass(frozen=True)
class FinancialSnapshot:
    verified_sales_count:int
    gross_revenue:float
    expenses:float
    net_profit:float
    currency:str
    def __post_init__(self):
        if self.verified_sales_count<0 or self.gross_revenue<0 or self.expenses<0: raise ValueError("Financial figures cannot be negative.")
