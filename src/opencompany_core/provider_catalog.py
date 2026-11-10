"""Conservative inventory of possible zero-cost model routes.

A listing here is not an enabled provider or a promise of permanent free access.
The runtime gateway remains closed unless a provider is explicitly configured.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderCandidate:
    key: str
    display_name: str
    access_mode: str
    current_free_evidence: str
    limits_or_conditions: tuple[str, ...]
    activation_gate: str


CANDIDATES = (
    ProviderCandidate(
        key="unorouter-free-models",
        display_name="UnoRouter free API models",
        access_mode="OpenAI-compatible chat completions API",
        current_free_evidence="Owner-configured account catalogue and explicit :free model selection are required; free availability and account quotas must be checked at use time.",
        limits_or_conditions=(
            "Only an explicitly selected model ID ending in :free is eligible for automatic company routing.",
            "The adapter never selects paid model IDs and never performs paid fallback.",
            "Provider-side free availability, rate limits, and account entitlements can change.",
            "A provider-reported non-zero cost is rejected by the zero-cost gateway policy.",
        ),
        activation_gate="Owner configures the UnoRouter API key, selects an account-accessible :free model, and sets OPENCOMPANY_CONFIRM_UNOROUTER_FREE=true.",
    ),
    ProviderCandidate(
        key="openrouter-free-models",
        display_name="OpenRouter free model variants",
        access_mode="OpenAI-compatible API",
        current_free_evidence="Provider currently lists models with $0 input and output pricing.",
        limits_or_conditions=(
            "Use only model IDs explicitly marked free (for example, :free variants).",
            "Free-model variants have low request quotas; current published baseline is 20 requests/minute and 50/day without a qualifying credit purchase.",
            "Do not buy credits to increase limits; never use paid model IDs or paid fallback routing.",
            "Free-model availability and provider-side limits can change.",
        ),
        activation_gate="Owner supplies a key and explicitly confirms the selected model ID is free at activation time.",
    ),
    ProviderCandidate(
        key="groq-developer-api",
        display_name="Groq API",
        access_mode="OpenAI-compatible API",
        current_free_evidence="Published model rate-limit documentation exists; the exact account's billing eligibility must be verified in its console.",
        limits_or_conditions=(
            "Limits vary by model and account tier.",
            "A rate limit alone does not prove that all usage is free.",
            "No model is activated until the account confirms a zero-cost allowance.",
        ),
        activation_gate="Verify zero-cost account entitlement and model pricing before configuring the adapter.",
    ),
    ProviderCandidate(
        key="cloudflare-workers-ai",
        display_name="Cloudflare Workers AI",
        access_mode="Cloudflare API",
        current_free_evidence="Published free Workers allocation includes 10,000 Neurons per day.",
        limits_or_conditions=(
            "Usage above the free allocation can be billable on a paid Workers plan.",
            "Some models require a paid billing method.",
            "Configure hard daily limits and fail closed at the free allocation; no paid overage.",
        ),
        activation_gate="Verify the chosen model is eligible for the free allocation and configure hard stop before activation.",
    ),
)


def free_provider_candidates() -> tuple[ProviderCandidate, ...]:
    return CANDIDATES
