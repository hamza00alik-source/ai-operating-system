"""Provider-neutral language-model access with fail-closed cost controls.

No provider is enabled by default. A provider adapter must be supplied by the
application; this module performs no network requests itself.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class BillingMode(StrEnum):
    DISABLED = "disabled"
    FREE_CONFIRMED = "free_confirmed"
    PAID_OWNER_APPROVED = "paid_owner_approved"


class NoEligibleProvider(RuntimeError):
    pass


class ProviderUnavailable(RuntimeError):
    pass


class CostPolicyViolation(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ModelRequest:
    prompt: str
    request_id: str
    max_output_tokens: int = 1200
    work_item_id: str = "system"
    role_key: str = "system"

    def __post_init__(self) -> None:
        if not self.prompt.strip():
            raise ValueError("prompt cannot be empty")
        if not self.request_id.strip():
            raise ValueError("request_id cannot be empty")
        if not self.work_item_id.strip() or not self.role_key.strip():
            raise ValueError("model request accounting identity cannot be empty")
        if not 1 <= self.max_output_tokens <= 16000:
            raise ValueError("max_output_tokens must be between 1 and 16000")


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    name: str
    model: str
    billing_mode: BillingMode = BillingMode.DISABLED
    max_cost_per_request_usd: float = 0.0
    priority: int = 100

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.model.strip():
            raise ValueError("provider name and model are required")
        if not math.isfinite(self.max_cost_per_request_usd) or self.max_cost_per_request_usd < 0:
            raise ValueError("provider cost ceiling must be finite and non-negative")
        if self.billing_mode == BillingMode.FREE_CONFIRMED and self.max_cost_per_request_usd != 0:
            raise ValueError("confirmed-free providers must have a zero cost ceiling")
        if self.billing_mode == BillingMode.PAID_OWNER_APPROVED and self.max_cost_per_request_usd <= 0:
            raise ValueError("paid providers require an explicit positive cost ceiling")


@dataclass(frozen=True, slots=True)
class ModelResult:
    text: str
    provider: str
    model: str
    cost_usd: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("model response cannot be empty")
        if not self.provider.strip() or not self.model.strip():
            raise ValueError("model response must identify its provider and model")
        if not math.isfinite(self.cost_usd) or self.cost_usd < 0:
            raise ValueError("reported cost must be finite and non-negative")


class ModelAdapter(Protocol):
    def generate(self, request: ModelRequest, *, model: str) -> ModelResult:
        """Generate text using the named model or raise ProviderUnavailable."""


@dataclass(frozen=True, slots=True)
class _ConfiguredProvider:
    policy: ProviderPolicy
    adapter: ModelAdapter


class ModelGateway:
    """Select only explicitly enabled providers that fit the request budget."""

    def __init__(
        self, providers: tuple[_ConfiguredProvider, ...] = (),
        usage_recorder=None,
    ) -> None:
        names = [item.policy.name for item in providers]
        if len(set(names)) != len(names):
            raise ValueError("provider names must be unique")
        self._providers = tuple(sorted(providers, key=lambda item: (item.policy.priority, item.policy.name)))
        self._usage_recorder = usage_recorder

    def set_usage_recorder(self, recorder) -> None:
        self._usage_recorder = recorder

    @classmethod
    def configure(cls, entries: tuple[tuple[ProviderPolicy, ModelAdapter], ...]) -> "ModelGateway":
        return cls(tuple(_ConfiguredProvider(policy, adapter) for policy, adapter in entries))

    @staticmethod
    def _validate_budget(request_budget_usd: float) -> None:
        if not math.isfinite(request_budget_usd) or request_budget_usd < 0:
            raise ValueError("request budget must be finite and non-negative")

    def eligible_providers(self, *, request_budget_usd: float = 0.0) -> tuple[str, ...]:
        self._validate_budget(request_budget_usd)
        eligible = []
        for item in self._providers:
            policy = item.policy
            if policy.billing_mode == BillingMode.FREE_CONFIRMED:
                eligible.append(policy.name)
            elif (
                policy.billing_mode == BillingMode.PAID_OWNER_APPROVED
                and request_budget_usd > 0
                and policy.max_cost_per_request_usd <= request_budget_usd
            ):
                eligible.append(policy.name)
        return tuple(eligible)

    def complete(
        self,
        request: ModelRequest,
        *,
        request_budget_usd: float = 0.0,
        preferred_provider: str | None = None,
    ) -> ModelResult:
        self._validate_budget(request_budget_usd)
        available = [
            item for item in self._providers
            if item.policy.name in self.eligible_providers(request_budget_usd=request_budget_usd)
        ]
        if preferred_provider:
            available = sorted(
                available,
                key=lambda item: (item.policy.name != preferred_provider,
                                  item.policy.priority, item.policy.name),
            )
        if not available:
            raise NoEligibleProvider("No explicitly enabled provider fits the current cost policy.")

        failures = []
        for item in available:
            try:
                result = item.adapter.generate(request, model=item.policy.model)
            except ProviderUnavailable as exc:
                failures.append(f"{item.policy.name}: {exc}")
                continue
            dynamic_free_catalog = (
                item.policy.name == "unorouter"
                and item.policy.model == "unorouter/free-catalog:free"
                and isinstance(result.model, str)
                and result.model.endswith(":free")
            )
            if result.provider != item.policy.name or (
                result.model != item.policy.model and not dynamic_free_catalog
            ):
                raise CostPolicyViolation("adapter response identity does not match selected provider")
            if self._usage_recorder is not None:
                try:
                    self._usage_recorder({
                        "request_id": request.request_id,
                        "work_item_id": request.work_item_id,
                        "role_key": request.role_key,
                        "provider": result.provider,
                        "model": result.model,
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "cost_usd": result.cost_usd,
                    })
                except Exception as exc:
                    raise CostPolicyViolation("model result could not be durably recorded; execution is blocked") from exc
            if item.policy.billing_mode == BillingMode.FREE_CONFIRMED and result.cost_usd != 0:
                raise CostPolicyViolation("provider reported a charge under a zero-cost policy")
            if result.cost_usd > request_budget_usd:
                raise CostPolicyViolation("provider-reported cost exceeds the request budget")
            if result.cost_usd > item.policy.max_cost_per_request_usd:
                raise CostPolicyViolation("provider-reported cost exceeds its configured ceiling")
            return result
        if failures:
            raise ProviderUnavailable(
                "All eligible providers were unavailable: " + "; ".join(failures)
            )
        raise NoEligibleProvider("No explicitly enabled provider fits the current cost policy.")
