"""Cost-bounded provider routing with explicit free-tier confirmation."""
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable
import json
import os
import urllib.error
import urllib.request


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


class UnoRouterFreeAdapter:
    """OpenAI-compatible UnoRouter adapter restricted to explicitly :free models."""
    endpoint = "https://api.unorouter.com/v1/chat/completions"

    def __init__(self, api_key: str, timeout_seconds: int = 45):
        if not api_key or not api_key.strip():
            raise ValueError("UnoRouter API key is required.")
        self._api_key = api_key.strip()
        self._timeout = max(5, min(int(timeout_seconds), 60))

    def generate(self, request: Any, *, model: str) -> ModelResult:
        if not isinstance(model, str) or not model.endswith(":free"):
            raise ProviderUnavailable("Only an explicitly free UnoRouter model is eligible.")
        prompt = request.get("prompt") if isinstance(request, dict) else str(request)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("A non-empty specialist prompt is required.")
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 1200,
        }).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                raw = response.read(1_000_000)
            data = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ProviderUnavailable(f"UnoRouter returned HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ProviderUnavailable("UnoRouter connection failed.") from exc
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ProviderUnavailable("UnoRouter returned an invalid response.") from exc
        choices = data.get("choices") if isinstance(data, dict) else None
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
        answer = message.get("content") if isinstance(message, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            raise ProviderUnavailable("UnoRouter returned no usable text.")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return ModelResult(
            text=answer.strip(), provider="unorouter",
            model=str(data.get("model") or model), cost_usd=0.0,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )


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
        raise ProviderUnavailable("All eligible providers were unavailable: "+("; ".join(failures) or "no confirmed zero-cost provider configured")+". No paid fallback was attempted.")


def gateway_from_environment():
    """Build a fail-closed gateway; configuration never implies paid fallback."""
    key=os.getenv("OPENCOMPANY_UNOROUTER_API_KEY","").strip()
    model=os.getenv("OPENCOMPANY_UNOROUTER_FREE_MODEL","").strip()
    confirmed=os.getenv("OPENCOMPANY_CONFIRM_UNOROUTER_FREE","").strip().lower()=="true"
    if not (key and model.endswith(":free") and confirmed):
        return ModelGateway.configure(())
    policy=ProviderPolicy("unorouter",model,BillingMode.FREE_CONFIRMED,0.0)
    return ModelGateway.configure(((policy,UnoRouterFreeAdapter(key),),))
