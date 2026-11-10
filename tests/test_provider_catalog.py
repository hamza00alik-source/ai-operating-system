from opencompany_core.provider_catalog import free_provider_candidates


def test_provider_candidates_are_discovery_only_and_have_activation_gates():
    candidates = free_provider_candidates()
    assert {item.key for item in candidates} == {
        "openrouter-free-models", "groq-developer-api", "cloudflare-workers-ai"
    }
    assert all(item.activation_gate for item in candidates)
    assert all(item.limits_or_conditions for item in candidates)
