"""Opt-in OpenAI-compatible model adapter. Disabled unless explicitly configured."""
import json, os, urllib.error, urllib.parse, urllib.request

class ModelNotConfigured(RuntimeError):
    pass

def get_model_status() -> dict:
    enabled = os.getenv("AI_OS_MODEL_ENABLED", "false").strip().lower() == "true"
    base_url = os.getenv("AI_OS_MODEL_BASE_URL", "").strip()
    model = os.getenv("AI_OS_MODEL_NAME", "").strip()
    configured = bool(base_url and model)
    return {"enabled": enabled and configured, "configured": configured,
            "provider": os.getenv("AI_OS_MODEL_PROVIDER", "openai_compatible").strip() or "openai_compatible",
            "model": model or None, "base_url_present": bool(base_url),
            "api_key_present": bool(os.getenv("AI_OS_MODEL_API_KEY", "").strip()),
            "reason": "ready" if enabled and configured else ("disabled_by_default" if not enabled else "missing_base_url_or_model"),
            "makes_network_request": False}

def _endpoint(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    if parsed.scheme != "https" and not (local and parsed.scheme == "http"):
        raise ValueError("Model endpoint must use HTTPS; only localhost may use HTTP.")
    if parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("Model endpoint URL is invalid.")
    clean = base_url.rstrip("/")
    return clean if clean.endswith("/chat/completions") else clean + "/chat/completions"

def generate_json(system_prompt: str, user_prompt: str) -> tuple[dict, dict]:
    status = get_model_status()
    if not status["enabled"]:
        raise ModelNotConfigured("Model execution is disabled or not configured. No provider request was made.")
    base_url, model = os.getenv("AI_OS_MODEL_BASE_URL", "").strip(), os.getenv("AI_OS_MODEL_NAME", "").strip()
    timeout = max(5, min(int(os.getenv("AI_OS_MODEL_TIMEOUT_SECONDS", "45")), 90))
    body = {"model": model, "temperature": 0.2, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]}
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = os.getenv("AI_OS_MODEL_API_KEY", "").strip()
    if key:
        headers["Authorization"] = "Bearer " + key
    request = urllib.request.Request(_endpoint(base_url), data=json.dumps(body).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("Model provider request failed. Check provider availability and configuration.") from exc
    try:
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not isinstance(content, str):
            raise TypeError("Model content is not text")
        cleaned = content.strip()
        fence = chr(96) * 3
        if cleaned.startswith(fence):
            cleaned = cleaned.split("\n", 1)[1].rsplit(fence, 1)[0].strip()
        result = json.loads(cleaned)
        if not isinstance(result, dict):
            raise ValueError("Expected a JSON object")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Model returned an invalid structured review.") from exc
    return result, {"provider": status["provider"], "model": model}
