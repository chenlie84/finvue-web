"""Server-side AI route manager with fallback support."""
from __future__ import annotations

from typing import Any

import httpx

import store


def _text(value: Any) -> str:
    return str(value or "").strip()


def _provider_label(provider: dict[str, Any]) -> str:
    return _text(provider.get("label") or provider.get("id") or provider.get("baseUrl") or "AI 路由")


def _extract_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    output = data.get("output")
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            for block in (item or {}).get("content") or []:
                if isinstance(block, dict):
                    parts.append(str(block.get("text") or ""))
        if parts:
            return "".join(parts)
    return ""


def _build_request(provider: dict[str, Any], system_prompt: str, user_prompt: str) -> tuple[str, dict[str, Any]]:
    base_url = _text(provider.get("baseUrl") or provider.get("url")).rstrip("/")
    model = _text(provider.get("model"))
    if not base_url:
        raise ValueError("AI 路由缺少 baseUrl")
    if not model:
        raise ValueError("AI 路由缺少 model")
    if base_url.endswith("/chat/completions"):
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
    else:
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
        }
    return base_url, payload


def _call_provider(provider: dict[str, Any], system_prompt: str, user_prompt: str) -> str:
    api_key = _text(provider.get("apiKey") or provider.get("key"))
    if not api_key:
        raise ValueError("AI 路由缺少 API Key")
    url, payload = _build_request(provider, system_prompt, user_prompt)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    timeout = float(provider.get("timeoutSeconds") or 180)
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"{response.status_code}: {response.text[:500]}")
    text = _extract_text(response.json())
    if not text:
        raise RuntimeError("模型返回为空")
    return text


def _routes_from_payload(payload: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    inline = {
        "id": "request-inline",
        "label": payload.get("routeLabel") or "本次请求路由",
        "baseUrl": payload.get("baseUrl") or payload.get("apiBaseUrl"),
        "apiKey": payload.get("apiKey"),
        "model": payload.get("model"),
        "enabled": bool(payload.get("apiKey") and payload.get("model")),
        "priority": 0,
    }
    routes = [inline] if inline["enabled"] else []
    for route in settings.get("aiProviders") or []:
        if isinstance(route, dict) and route.get("enabled", True):
            routes.append(route)
    return sorted(routes, key=lambda item: int(item.get("priority") or 999))


def generate(payload: dict[str, Any], username: str | None = None) -> dict[str, Any]:
    settings = store.get_effective_settings(username)
    role_prompt = _text(payload.get("anchorRolePrompt") or settings.get("anchorRolePrompt"))
    system_prompt = _text(payload.get("systemPrompt") or settings.get("systemPrompt") or role_prompt)
    user_prompt = _text(payload.get("userPrompt") or settings.get("userPrompt"))
    transcript = _text(payload.get("transcriptText") or payload.get("transcript") or payload.get("content"))
    live_data = _text(payload.get("liveData") or payload.get("data") or payload.get("extraContext"))
    hot_topics = _text(payload.get("externalHotTopics") or settings.get("externalHotTopics"))
    user_input = "\n\n".join(part for part in [user_prompt, hot_topics and f"外部热点：\n{hot_topics}", live_data and f"直播数据：\n{live_data}", transcript and f"逐字稿：\n{transcript}"] if part)
    attempts: list[dict[str, str]] = []
    for provider in _routes_from_payload(payload, settings):
        label = _provider_label(provider)
        try:
            markdown = _call_provider(provider, system_prompt, user_input)
            return {
                "markdown": markdown,
                "aiMeta": {
                    "provider": label,
                    "route": _text(provider.get("id") or label),
                    "model": _text(provider.get("model")),
                    "attempts": attempts,
                },
            }
        except Exception as exc:
            attempts.append({"provider": label, "model": _text(provider.get("model")), "error": str(exc)})
            continue
    detail = "；".join(f"{item['provider']}：{item['error']}" for item in attempts) or "未配置可用 AI 路由"
    raise RuntimeError(f"AI 生成失败：{detail}")
