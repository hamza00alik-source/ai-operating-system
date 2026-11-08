"""One-request, no-key smoke test for the public OVHcloud OpenAI-compatible endpoint.

This is a connectivity check only; it does not enable the provider in AIOS or
prove a production SLA. The endpoint is public and rate-limited.
"""
import json
import urllib.error
import urllib.request

ENDPOINT = "https://oai.endpoints.kepler.ai.cloud.ovh.net/v1/chat/completions"
MODEL = "gpt-oss-20b"


def main() -> None:
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    'Return only a JSON object with exactly these keys: '
                    '{"status":"ok","summary":"public model reachable"}.'
                ),
            }
        ],
        "temperature": 0,
        "max_tokens": 120,
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            if not 200 <= response.status < 300:
                raise RuntimeError(f"Public model returned HTTP {response.status}.")
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"Public model smoke test failed: HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Public model smoke test failed: {type(exc).__name__}; no credentials were used."
        ) from exc

    choices = result.get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else None
    if not isinstance(content, str) or not content.strip():
        raise SystemExit("Public model responded but returned no chat content.")
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        decoded = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise SystemExit("Public model responded, but did not follow the JSON smoke-test prompt.") from exc
    if not isinstance(decoded, dict) or decoded.get("status") != "ok":
        raise SystemExit("Public model responded, but its structured result was unexpected.")
    print(f"PASS: {MODEL} responded successfully without an API key.")
    print("This confirms endpoint connectivity only; it does not verify AIOS production configuration.")


if __name__ == "__main__":
    main()
