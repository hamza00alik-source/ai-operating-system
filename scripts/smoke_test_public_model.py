"""One-request smoke test of AIOS's actual adapter against the no-key OVH endpoint."""
import os

# Use only the exact public anonymous endpoint and allowlisted model. No API key
# or fallback provider is configured for this smoke test.
os.environ["AI_OS_MODEL_ENABLED"] = "true"
os.environ["AI_OS_MODEL_BACKEND"] = "openai_compatible"
os.environ["AI_OS_MODEL_PROVIDER"] = "ovhcloud-anonymous"
os.environ["AI_OS_MODEL_BASE_URL"] = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1"
os.environ["AI_OS_MODEL_NAME"] = "gpt-oss-20b"
os.environ["AI_OS_MODEL_API_KEY"] = ""
os.environ["AI_OS_FREE_ONLY"] = "true"
os.environ["AI_OS_FREE_MODEL_ALLOWLIST"] = "gpt-oss-20b"

from ai_os.model_adapter import generate_json


def main() -> None:
    try:
        result, provider = generate_json(
            "You are a connectivity test. Return a valid JSON object only.",
            'Return {"status":"completed","summary":"AIOS adapter connected"} exactly.',
        )
    except Exception as exc:
        raise SystemExit(
            f"AIOS adapter smoke test failed: {type(exc).__name__}. No credentials were used."
        ) from exc

    if not isinstance(result, dict) or result.get("status") != "completed":
        raise SystemExit("AIOS adapter received a response, but its structured result was invalid.")
    if provider.get("provider") != "ovhcloud-anonymous" or provider.get("model") != "gpt-oss-20b":
        raise SystemExit("AIOS adapter used an unexpected provider or model.")
    print("PASS: AIOS model adapter received a valid response from gpt-oss-20b without an API key.")
    print("No paid fallback was enabled; this is a connectivity smoke test, not a production SLA.")


if __name__ == "__main__":
    main()
