"""Transparent opportunity scoring; all inputs are normalized 0..100."""
from dataclasses import dataclass
from opencompany.domain import Opportunity

@dataclass(frozen=True)
class ScoreBreakdown:
    demand: float
    buyer_access: float
    margin: float
    feasibility: float
    differentiation: float
    cost_risk: float
    total: float

def score_opportunity(item: Opportunity) -> ScoreBreakdown:
    values = [item.demand_evidence, item.buyer_access, item.margin_potential, item.ai_feasibility, item.differentiation, item.cost_risk]
    if any(not 0 <= v <= 100 for v in values):
        raise ValueError("All scoring inputs must be between 0 and 100.")
    total = (item.demand_evidence * .25 + item.buyer_access * .20 + item.margin_potential * .20 +
             item.ai_feasibility * .15 + item.differentiation * .10 + item.cost_risk * .10)
    return ScoreBreakdown(*values, total=round(total, 2))
