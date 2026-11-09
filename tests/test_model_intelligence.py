from ai_os import model_intelligence


def test_provider_intelligence_reports_only_owner_confirmed_gateway_state(monkeypatch):
    monkeypatch.setattr(model_intelligence, "list_providers", lambda: [
        {"id": "free-a", "name": "Free A", "configured": True, "free_confirmed": True,
         "eligible": True, "experimental_only": False, "model": "model-a", "reason": None},
        {"id": "paid-b", "name": "Paid B", "configured": True, "free_confirmed": False,
         "eligible": False, "experimental_only": False, "model": "model-b", "reason": "Not confirmed"},
        {"id": "unset-c", "name": "Unset C", "configured": False, "free_confirmed": False,
         "eligible": False, "experimental_only": False, "model": None, "reason": "Not configured"},
    ])
    result = model_intelligence.provider_intelligence()
    assert result["summary"] == {
        "known_providers": 3,
        "configured_providers": 2,
        "free_confirmed_eligible": 1,
        "configured_but_blocked": 1,
    }
    assert result["mode"].startswith("configuration-only")
    assert "does not guarantee" in result["safety_note"]
    assert all("secret" not in str(provider).lower() for provider in result["providers"])
