"""Evidence-aware model/provider intelligence derived from the existing safe gateway."""
from __future__ import annotations

from datetime import datetime, timezone
from ai_os.llm_gateway import list_providers


def provider_intelligence() -> dict:
    """Summarize configured providers without probing or invoking paid inference."""
    providers = list_providers()
    eligible = [p for p in providers if p.get("eligible")]
    configured = [p for p in providers if p.get("configured")]
    blocked = [p for p in configured if not p.get("eligible")]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "AIOS configured provider gateway",
        "mode": "configuration-only; no network probes or inference",
        "summary": {
            "known_providers": len(providers),
            "configured_providers": len(configured),
            "free_confirmed_eligible": len(eligible),
            "configured_but_blocked": len(blocked),
        },
        "providers": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "configured": bool(p.get("configured")),
                "free_confirmed": bool(p.get("free_confirmed")),
                "eligible": bool(p.get("eligible")),
                "experimental_only": bool(p.get("experimental_only")),
                "model": p.get("model"),
                "reason": p.get("reason"),
                "evidence": "owner-confirmed configuration; not an independent price/terms verification",
            }
            for p in providers
        ],
        "safety_note": (
            "Eligibility reflects the owner's explicit free-tier confirmation and gateway rules. "
            "It does not guarantee provider quotas, availability, or future pricing. Re-verify "
            "provider terms before enabling or routing workload."
        ),
    }
