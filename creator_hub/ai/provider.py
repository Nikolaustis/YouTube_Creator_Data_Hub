from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AIUnavailable(RuntimeError):
    pass


class AILocalBudgetExceeded(RuntimeError):
    pass


@dataclass
class AIResponse:
    data: dict[str, Any]
    response_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    raw_status: str = "completed"


PROTOCOLS = {
    "openai_responses": {
        "label": "Responses API",
        "default_base_url": "https://api.openai.com/v1",
        "key_hint": "Bearer API key",
    },
    "openai_chat": {
        "label": "OpenAI-compatible Chat Completions",
        "default_base_url": "https://api.openai.com/v1",
        "key_hint": "Bearer API key",
    },
    "anthropic_messages": {
        "label": "Anthropic Messages",
        "default_base_url": "https://api.anthropic.com/v1",
        "key_hint": "x-api-key",
    },
    "gemini_generate_content": {
        "label": "Gemini generateContent",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta",
        "key_hint": "x-goog-api-key",
    },
    "mock": {
        "label": "Mock (offline test)",
        "default_base_url": "",
        "key_hint": "No API key required",
    },
    "disabled": {
        "label": "Disabled",
        "default_base_url": "",
        "key_hint": "",
    },
}

GENERIC_KEY_ENV = "CREATOR_HUB_AI_API_KEY"
_SECRET_FILE = Path.home() / ".youtube_creator_data_hub" / "ai_api_key"


def protocol_default_base_url(protocol: str) -> str:
    return str((PROTOCOLS.get(str(protocol or "").lower()) or {}).get("default_base_url") or "")


def _legacy_protocol(provider: str) -> str:
    p = str(provider or "").strip().lower()
    return {
        "openai": "openai_responses",
        "mock": "mock",
        "disabled": "disabled",
    }.get(p, p or "openai_responses")


def resolved_ai_config(settings: dict[str, Any], persisted: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(settings.get("ai") or {})
    persisted = dict(persisted or {})
    if persisted:
        base.update({k: v for k, v in persisted.items() if v is not None})

    # v3.0 persisted only ``provider``. v3.1 adds ``protocol`` to the shipped
    # settings, so an old persisted provider must still override that new default.
    if persisted.get("protocol"):
        protocol = str(persisted.get("protocol")).lower()
    elif persisted.get("provider"):
        protocol = _legacy_protocol(str(persisted.get("provider"))).lower()
    else:
        protocol = str(base.get("protocol") or _legacy_protocol(base.get("provider") or "openai")).lower()
    if protocol not in PROTOCOLS:
        protocol = "openai_chat"
    base["protocol"] = protocol
    # Keep provider as a compatibility/readability alias for old run history/UI code.
    base["provider"] = protocol

    enabled_env = os.environ.get("CREATOR_HUB_AI_ENABLED")
    if enabled_env is not None:
        base["enabled"] = enabled_env.strip().lower() in {"1", "true", "yes", "on"}
    if os.environ.get("CREATOR_HUB_AI_PROTOCOL"):
        base["protocol"] = os.environ["CREATOR_HUB_AI_PROTOCOL"].strip().lower()
        base["provider"] = base["protocol"]
    elif os.environ.get("CREATOR_HUB_AI_PROVIDER"):
        base["protocol"] = _legacy_protocol(os.environ["CREATOR_HUB_AI_PROVIDER"])
        base["provider"] = base["protocol"]
    if os.environ.get("CREATOR_HUB_AI_MODEL"):
        base["model"] = os.environ["CREATOR_HUB_AI_MODEL"].strip()
    if os.environ.get("CREATOR_HUB_AI_BASE_URL"):
        base["base_url"] = os.environ["CREATOR_HUB_AI_BASE_URL"].strip()

    base.setdefault("enabled", False)
    base.setdefault("model", "")
    base.setdefault("api_key_env", GENERIC_KEY_ENV)
    if not str(base.get("api_key_env") or "").strip() or str(base.get("api_key_env")) == "OPENAI_API_KEY":
        # v3.1 uses a provider-neutral key slot; OPENAI_API_KEY remains a read-only fallback.
        base["api_key_env"] = GENERIC_KEY_ENV
    if not str(base.get("base_url") or "").strip():
        base["base_url"] = protocol_default_base_url(base["protocol"])
    base.setdefault("timeout_seconds", 60)
    base.setdefault("daily_request_soft_limit", 100)
    base.setdefault("max_creators_per_task", 50)
    base.setdefault("send_contact_data", False)
    base.setdefault("store_remote", False)
    return base


def _secret_file_key() -> str:
    try:
        return _SECRET_FILE.read_text(encoding="utf-8").strip() if _SECRET_FILE.exists() else ""
    except Exception:
        return ""


def read_ai_api_key(cfg: dict[str, Any], override: str | None = None) -> tuple[str, str]:
    # Offline/local protocols must never inspect or expose a user's real API key.
    # This also keeps upgrade self-checks deterministic on machines where the
    # provider-neutral CREATOR_HUB_AI_API_KEY is already configured.
    protocol = str(cfg.get("protocol") or cfg.get("provider") or "").strip().lower()
    if protocol in {"mock", "disabled"}:
        return "", ""
    if override is not None and str(override).strip():
        return str(override).strip(), "request"
    env = str(cfg.get("api_key_env") or GENERIC_KEY_ENV)
    value = os.environ.get(env, "").strip()
    if value:
        return value, env
    protocol = str(cfg.get("protocol") or "")
    legacy = []
    if protocol in {"openai_responses", "openai_chat"}:
        legacy += ["OPENAI_API_KEY", "OPENROUTER_API_KEY"]
    elif protocol == "anthropic_messages":
        legacy += ["ANTHROPIC_API_KEY"]
    elif protocol == "gemini_generate_content":
        legacy += ["GEMINI_API_KEY", "GOOGLE_API_KEY"]
    for name in legacy:
        value = os.environ.get(name, "").strip()
        if value:
            return value, name
    value = _secret_file_key()
    return (value, "user-secret-file") if value else ("", "")


def persist_ai_api_key(key: str, env_name: str = GENERIC_KEY_ENV) -> dict[str, Any]:
    value = str(key or "").strip()
    if not value:
        raise ValueError("API Key cannot be empty")
    os.environ[env_name] = value
    persisted = False
    location = "current-process"
    if os.name == "nt":
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as reg:
                winreg.SetValueEx(reg, env_name, 0, winreg.REG_SZ, value)
            persisted = True
            location = f"Windows user environment: {env_name}"
        except Exception as exc:
            raise AIUnavailable(f"Failed to persist Windows user API key: {exc}") from exc
    else:
        try:
            _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SECRET_FILE.write_text(value, encoding="utf-8")
            try:
                os.chmod(_SECRET_FILE, 0o600)
            except Exception:
                pass
            persisted = True
            location = str(_SECRET_FILE)
        except Exception as exc:
            raise AIUnavailable(f"Failed to persist local API key: {exc}") from exc
    return {"persisted": persisted, "location": location, "env_name": env_name}


def clear_ai_api_key(env_name: str = GENERIC_KEY_ENV) -> dict[str, Any]:
    os.environ.pop(env_name, None)
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE) as reg:
                try:
                    winreg.DeleteValue(reg, env_name)
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass
        except Exception as exc:
            raise AIUnavailable(f"Failed to clear Windows user API key: {exc}") from exc
    try:
        if _SECRET_FILE.exists():
            _SECRET_FILE.unlink()
    except Exception:
        pass
    return {"cleared": True, "env_name": env_name}


def _validate_base_url(url: str) -> str:
    u = str(url or "").strip().rstrip("/")
    if not u:
        raise ValueError("API Base URL is required for this protocol")
    parsed = urllib.parse.urlparse(u)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("API Base URL must be an http:// or https:// URL")
    return u


def _endpoint(base_url: str, suffix: str) -> str:
    base = _validate_base_url(base_url)
    suffix = "/" + suffix.lstrip("/")
    return base if base.endswith(suffix) else base + suffix


def _request_json(url: str, *, method: str = "POST", headers: dict[str, str] | None = None,
                  body: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        raise AIUnavailable(f"AI HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise AIUnavailable(f"AI request failed: {exc}") from exc


def _schema_instruction(prompt: str, schema: dict[str, Any]) -> str:
    return (
        prompt
        + "\n\nReturn ONLY one valid JSON object. Do not use Markdown fences. "
        + "The JSON must conform to this schema: "
        + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
    )


def _parse_json_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise AIUnavailable("AI returned invalid JSON")
        try:
            obj = json.loads(raw[start:end + 1])
        except Exception as exc:
            raise AIUnavailable("AI returned invalid JSON") from exc
    if not isinstance(obj, dict):
        raise AIUnavailable("AI JSON result must be an object")
    return obj


class DisabledProvider:
    name = "disabled"

    def __init__(self, reason: str = "AI is disabled"):
        self.reason = reason

    @property
    def available(self) -> bool:
        return False

    def generate_json(self, *args, **kwargs):
        raise AIUnavailable(self.reason)

    def list_models(self) -> list[str]:
        return []


class MockProvider:
    name = "mock"

    @property
    def available(self) -> bool:
        return True

    def generate_json(self, *, task: str, prompt: str, schema: dict[str, Any], model: str,
                      mock_data: dict[str, Any] | None = None) -> AIResponse:
        return AIResponse(data=dict(mock_data or {}), response_id="mock-" + uuid.uuid4().hex[:12])

    def list_models(self) -> list[str]:
        return ["mock-v1"]


class _HTTPProvider:
    name = "http"

    def __init__(self, cfg: dict[str, Any], api_key_override: str | None = None):
        self.cfg = cfg
        self.key, self.key_source = read_ai_api_key(cfg, api_key_override)

    @property
    def available(self) -> bool:
        return bool(self.key and str(self.cfg.get("model") or "").strip() and str(self.cfg.get("base_url") or "").strip())

    @property
    def timeout(self) -> int:
        return int(self.cfg.get("timeout_seconds") or 60)


class OpenAIResponsesProvider(_HTTPProvider):
    name = "openai_responses"

    def generate_json(self, *, task: str, prompt: str, schema: dict[str, Any], model: str,
                      mock_data: dict[str, Any] | None = None) -> AIResponse:
        if not self.key:
            raise AIUnavailable("Missing AI API key")
        body = {
            "model": model,
            "input": prompt,
            "store": bool(self.cfg.get("store_remote", False)),
            "text": {"format": {"type": "json_schema", "name": task.replace("-", "_")[:64], "schema": schema, "strict": True}},
        }
        payload = _request_json(
            _endpoint(str(self.cfg.get("base_url") or protocol_default_base_url(self.name)), "/responses"),
            headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json", "X-Client-Request-Id": str(uuid.uuid4()), "User-Agent": "YouTube-Creator-Data-Hub/3.9.0"},
            body=body, timeout=self.timeout,
        )
        text = payload.get("output_text") or ""
        if not text:
            for item in payload.get("output") or []:
                for part in item.get("content") or []:
                    if part.get("type") == "output_text" and part.get("text"):
                        text += str(part["text"])
        parsed = _parse_json_text(text)
        usage = payload.get("usage") or {}
        return AIResponse(parsed, str(payload.get("id") or ""), int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0), str(payload.get("status") or "completed"))

    def list_models(self) -> list[str]:
        payload = _request_json(_endpoint(str(self.cfg.get("base_url")), "/models"), method="GET", headers={"Authorization": "Bearer " + self.key, "User-Agent": "YouTube-Creator-Data-Hub/3.9.0"}, timeout=self.timeout)
        return sorted({str(x.get("id")) for x in payload.get("data") or [] if isinstance(x, dict) and x.get("id")})


class OpenAIChatProvider(_HTTPProvider):
    name = "openai_chat"

    def _call(self, body: dict[str, Any]) -> dict[str, Any]:
        return _request_json(_endpoint(str(self.cfg.get("base_url")), "/chat/completions"), headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json", "User-Agent": "YouTube-Creator-Data-Hub/3.9.0"}, body=body, timeout=self.timeout)

    def generate_json(self, *, task: str, prompt: str, schema: dict[str, Any], model: str,
                      mock_data: dict[str, Any] | None = None) -> AIResponse:
        if not self.key:
            raise AIUnavailable("Missing AI API key")
        p = _schema_instruction(prompt, schema)
        body = {
            "model": model,
            "messages": [{"role": "user", "content": p}],
            "response_format": {"type": "json_schema", "json_schema": {"name": task.replace("-", "_")[:64], "strict": True, "schema": schema}},
        }
        try:
            payload = self._call(body)
        except AIUnavailable as exc:
            # Many OpenAI-compatible gateways support chat/completions but not json_schema.
            if "400" not in str(exc) and "422" not in str(exc):
                raise
            body.pop("response_format", None)
            payload = self._call(body)
        choice = (payload.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        content = msg.get("content") or ""
        if isinstance(content, list):
            content = "".join(str(x.get("text") or "") for x in content if isinstance(x, dict))
        parsed = _parse_json_text(str(content))
        usage = payload.get("usage") or {}
        return AIResponse(parsed, str(payload.get("id") or ""), int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0), "completed")

    def list_models(self) -> list[str]:
        payload = _request_json(_endpoint(str(self.cfg.get("base_url")), "/models"), method="GET", headers={"Authorization": "Bearer " + self.key, "User-Agent": "YouTube-Creator-Data-Hub/3.9.0"}, timeout=self.timeout)
        return sorted({str(x.get("id")) for x in payload.get("data") or [] if isinstance(x, dict) and x.get("id")})


class AnthropicMessagesProvider(_HTTPProvider):
    name = "anthropic_messages"

    def _headers(self) -> dict[str, str]:
        return {"x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json", "User-Agent": "YouTube-Creator-Data-Hub/3.9.0"}

    def generate_json(self, *, task: str, prompt: str, schema: dict[str, Any], model: str,
                      mock_data: dict[str, Any] | None = None) -> AIResponse:
        if not self.key:
            raise AIUnavailable("Missing AI API key")
        body = {"model": model, "max_tokens": 4096, "messages": [{"role": "user", "content": _schema_instruction(prompt, schema)}]}
        payload = _request_json(_endpoint(str(self.cfg.get("base_url")), "/messages"), headers=self._headers(), body=body, timeout=self.timeout)
        text = "".join(str(x.get("text") or "") for x in payload.get("content") or [] if isinstance(x, dict) and x.get("type") == "text")
        parsed = _parse_json_text(text)
        usage = payload.get("usage") or {}
        return AIResponse(parsed, str(payload.get("id") or ""), int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0), str(payload.get("stop_reason") or "completed"))

    def list_models(self) -> list[str]:
        payload = _request_json(_endpoint(str(self.cfg.get("base_url")), "/models"), method="GET", headers=self._headers(), timeout=self.timeout)
        return sorted({str(x.get("id")) for x in payload.get("data") or [] if isinstance(x, dict) and x.get("id")})


class GeminiGenerateContentProvider(_HTTPProvider):
    name = "gemini_generate_content"

    def generate_json(self, *, task: str, prompt: str, schema: dict[str, Any], model: str,
                      mock_data: dict[str, Any] | None = None) -> AIResponse:
        if not self.key:
            raise AIUnavailable("Missing AI API key")
        base = _validate_base_url(str(self.cfg.get("base_url")))
        model_id = str(model or "").removeprefix("models/")
        url = f"{base}/models/{urllib.parse.quote(model_id, safe='-_.')}:generateContent"
        body = {"contents": [{"parts": [{"text": _schema_instruction(prompt, schema)}]}], "generationConfig": {"responseMimeType": "application/json"}}
        payload = _request_json(url, headers={"x-goog-api-key": self.key, "Content-Type": "application/json", "User-Agent": "YouTube-Creator-Data-Hub/3.9.0"}, body=body, timeout=self.timeout)
        parts = (((payload.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        text = "".join(str(x.get("text") or "") for x in parts if isinstance(x, dict))
        parsed = _parse_json_text(text)
        usage = payload.get("usageMetadata") or {}
        return AIResponse(parsed, str(payload.get("responseId") or ""), int(usage.get("promptTokenCount") or 0), int(usage.get("candidatesTokenCount") or 0), "completed")

    def list_models(self) -> list[str]:
        base = _validate_base_url(str(self.cfg.get("base_url")))
        payload = _request_json(base + "/models?pageSize=1000", method="GET", headers={"x-goog-api-key": self.key, "User-Agent": "YouTube-Creator-Data-Hub/3.9.0"}, timeout=self.timeout)
        out = []
        for x in payload.get("models") or []:
            if not isinstance(x, dict) or not x.get("name"):
                continue
            methods = set(x.get("supportedGenerationMethods") or [])
            if methods and "generateContent" not in methods:
                continue
            out.append(str(x["name"]).removeprefix("models/"))
        return sorted(set(out))


def make_provider(cfg: dict[str, Any], api_key_override: str | None = None):
    if not bool(cfg.get("enabled")):
        return DisabledProvider("AI is disabled")
    protocol = str(cfg.get("protocol") or _legacy_protocol(cfg.get("provider") or "openai")).lower()
    if protocol == "disabled":
        return DisabledProvider("AI provider is disabled")
    if protocol == "mock":
        return MockProvider()
    classes = {
        "openai_responses": OpenAIResponsesProvider,
        "openai_chat": OpenAIChatProvider,
        "anthropic_messages": AnthropicMessagesProvider,
        "gemini_generate_content": GeminiGenerateContentProvider,
    }
    cls = classes.get(protocol)
    if not cls:
        return DisabledProvider(f"Unsupported AI protocol: {protocol}")
    return cls(cfg, api_key_override=api_key_override)
