"""Cost-bounded provider routing with explicit free-tier confirmation."""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

class BillingMode(str,Enum):
    FREE_CONFIRMED="free_confirmed"
    PAID="paid"
    UNKNOWN="unknown"

class ProviderUnavailable(RuntimeError): pass

@dataclass(frozen=True)
class ProviderPolicy:
    name: str
    model: str
    billing_mode: BillingMode
    max_cost_per_request_usd: float = 0.0
    def __post_init__(self):
        if not self.name or not self.model: raise ValueError("provider and model are required")
        if self.max_cost_per_request_usd < 0: raise ValueError("provider cost limit cannot be negative")

@dataclass(frozen=True)
class ModelResult:
    text: str
    provider: str
    model: str
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

class ModelGateway:
    def __init__(self, providers=()):
        self.providers=tuple(providers); self._usage_recorder=None
    @classmethod
    def configure(cls, providers):
        return cls(providers)
    def set_usage_recorder(self, recorder):
        self._usage_recorder=recorder
    def eligible_providers(self, *, request_budget_usd=0.0):
        if request_budget_usd < 0: return ()
        return tuple((policy,adapter) for policy,adapter in self.providers
            if policy.billing_mode is BillingMode.FREE_CONFIRMED
            and policy.max_cost_per_request_usd == 0.0
            and request_budget_usd == 0.0)
    def generate(self, request: Any, *, request_budget_usd=0.0):
        failures=[]
        for policy,adapter in self.eligible_providers(request_budget_usd=request_budget_usd):
            try:
                result=adapter.generate(request,model=policy.model)
                if result.cost_usd != 0:
                    raise ProviderUnavailable("Provider violated the zero-cost policy.")
                if self._usage_recorder: self._usage_recorder(result)
                return result
            except Exception as exc:
                failures.append(f"{policy.name}: {exc}")
        raise ProviderUnavailable("All eligible providers were unavailable: "+"; ".join(failures)+". No paid fallback was attempted.")
