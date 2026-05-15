"""Server-side AI route manager with fallback support."""
from __future__ import annotations

from urllib.parse import urlparse
from typing import Any

import requests

import config
import store


def _text(value: Any) -> str:
    return str(value or "").strip()


def _provider_label(provider: dict[str, Any]) -> str:
    return _text(provider.get("label") or provider.get("id") or provider.get("baseUrl") or "AI 路由")


def _extract_text(data: dict[str, Any]) -> str:
    # 处理 Anthropic 协议响应（非流式）
    if isinstance(data.get("content"), list):
        parts: list[str] = []
        for block in data.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        if parts:
            return "".join(parts)

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
        parts2: list[str] = []
        for item in output:
            for block in (item or {}).get("content") or []:
                if isinstance(block, dict):
                    parts2.append(str(block.get("text") or ""))
        if parts2:
            return "".join(parts2)
    return ""


def _is_anthropic_endpoint(url: str) -> bool:
    """检测是否是 Anthropic 协议端点."""
    return "/v1/messages" in url


def _build_request(provider: dict[str, Any], system_prompt: str, user_prompt: str) -> tuple[str, dict[str, Any], dict[str, str]]:
    base_url = _text(provider.get("baseUrl") or provider.get("url")).rstrip("/")
    model = _text(provider.get("model"))
    api_format = _text(provider.get("apiFormat") or "finvue")
    if not base_url:
        raise ValueError("AI 路由缺少 baseUrl")
    if not model:
        raise ValueError("AI 路由缺少 model")

    headers = {"Content-Type": "application/json"}

    # 根据 apiFormat 设置或 URL 自动判断使用哪种协议
    use_anthropic = api_format == "anthropic" or _is_anthropic_endpoint(base_url)
    use_openai = api_format == "openai" or base_url.endswith("/chat/completions")

    # Anthropic 协议（Claude）
    if use_anthropic:
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": model,
            "max_tokens": 4096,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": user_prompt},
            ],
        }
        return base_url, payload, headers

    # OpenAI 协议
    if use_openai:
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
    return base_url, payload, headers


def _should_use_proxy(provider: dict[str, Any], url: str) -> bool:
    if "useProxy" in provider:
        return bool(provider.get("useProxy"))
    return url.startswith("https://") or "paas.corp" not in url


def _call_provider(provider: dict[str, Any], system_prompt: str, user_prompt: str) -> str:
    api_key = _text(provider.get("apiKey") or provider.get("key"))
    if not api_key:
        raise ValueError("AI 路由缺少 API Key")
    url, payload, headers = _build_request(provider, system_prompt, user_prompt)
    if _text(provider.get("apiKeyPlacement") or "header") == "body":
        payload["api_key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = float(provider.get("timeoutSeconds") or 180)
    proxy = (config.HTTPS_PROXY or config.HTTP_PROXY) if _should_use_proxy(provider, url) else None
    proxies = {"http": proxy, "https": proxy} if proxy else None
    response = requests.post(url, headers=headers, json=payload, timeout=timeout, proxies=proxies)
    if response.status_code >= 400:
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            public_host = urlparse(config.PUBLIC_BASE_URL).netloc
            route_host = urlparse(url).netloc
            if public_host and route_host == public_host:
                raise RuntimeError(
                    f"{response.status_code}: AI 路由地址返回了 FinVue 站点 HTML 页面。"
                    "当前模型 Base URL 可能配置成了本应用域名，请改为真实模型网关地址。"
                )
            raise RuntimeError(f"{response.status_code}: AI 路由地址返回 HTML 页面，可能不是有效的模型接口")
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
