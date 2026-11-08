"""Provider discovery catalogue.

This is metadata, not API access. Free tiers and terms change; entries stay
disabled until the owner verifies current official terms and configures access.
"""
PROVIDER_CATALOG = [
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "protocol": "openai_compatible",
        "credential": "account_api_key",
        "free_tier_possible": True,
        "default_enabled": False,
        "official_url": "https://openrouter.ai/docs",
    },
    {
        "id": "groq",
        "name": "Groq",
        "protocol": "openai_compatible",
        "credential": "account_api_key",
        "free_tier_possible": True,
        "default_enabled": False,
        "official_url": "https://console.groq.com/docs",
    },
    {
        "id": "cerebras",
        "name": "Cerebras",
        "protocol": "openai_compatible",
        "credential": "account_api_key",
        "free_tier_possible": True,
        "default_enabled": False,
        "official_url": "https://inference-docs.cerebras.ai/",
    },
    {
        "id": "google_ai_studio",
        "name": "Google AI Studio",
        "protocol": "provider_specific",
        "credential": "account_api_key",
        "free_tier_possible": True,
        "default_enabled": False,
        "official_url": "https://ai.google.dev/gemini-api/docs",
    },
    {
        "id": "huggingface",
        "name": "Hugging Face Inference",
        "protocol": "provider_specific_or_openai_compatible",
        "credential": "account_token",
        "free_tier_possible": True,
        "default_enabled": False,
        "official_url": "https://huggingface.co/docs/inference-providers",
    },
]


def list_providers() -> list[dict]:
    """Return a copy of public metadata only."""
    return [dict(item) for item in PROVIDER_CATALOG]
