"""Server-side AI route manager with fallback support."""
from __future__ import annotations

import json
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


def normalize_provider_url(base_url: str, api_format: str = "") -> str:
    """Normalize provider base URL to a concrete generation endpoint."""
    url = _text(base_url).rstrip("/")
    fmt = _text(api_format or "finvue")
    if not url:
        return ""
    lower = url.lower()
    if fmt == "openai":
        if lower.endswith("/chat/completions"):
            return url
        if lower.endswith(("/v1", "/v2", "/api/v1", "/api/v2", "/openai/v1")):
            return f"{url}/chat/completions"
        return f"{url}/v1/chat/completions"
    if fmt == "anthropic":
        if lower.endswith("/v1/messages"):
            return url
        if lower.endswith("/anthropic"):
            return f"{url}/v1/messages"
    return url


def is_openai_protocol_url(url: str, api_format: str = "") -> bool:
    normalized = normalize_provider_url(url, api_format)
    return _text(api_format) == "openai" or normalized.endswith("/chat/completions")


def _max_output_tokens(provider: dict[str, Any], fallback: int = 8192) -> int:
    """Return a bounded output budget so long-form reports are not cut off mid-section."""
    try:
        value = int(provider.get("maxOutputTokens") or fallback)
    except (TypeError, ValueError):
        value = fallback
    return max(1024, min(value, 32768))


def build_provider_request(provider: dict[str, Any], system_prompt: str, user_prompt: str, *, max_tokens: int = 4096) -> tuple[str, dict[str, Any], dict[str, str]]:
    return _build_request(provider, system_prompt, user_prompt, max_tokens=max_tokens)


def _build_request(provider: dict[str, Any], system_prompt: str, user_prompt: str, *, max_tokens: int = 4096) -> tuple[str, dict[str, Any], dict[str, str]]:
    raw_base_url = _text(provider.get("baseUrl") or provider.get("url"))
    model = _text(provider.get("model"))
    api_format = _text(provider.get("apiFormat") or "finvue")
    base_url = normalize_provider_url(raw_base_url, api_format)
    if not base_url:
        raise ValueError("AI 路由缺少 baseUrl")
    if not model:
        raise ValueError("AI 路由缺少 model")

    headers = {"Content-Type": "application/json"}

    # 根据 apiFormat 设置或 URL 自动判断使用哪种协议
    use_anthropic = api_format == "anthropic" or _is_anthropic_endpoint(base_url)
    use_openai = is_openai_protocol_url(base_url, api_format)

    # Anthropic 协议（Claude）
    if use_anthropic:
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "stream": False,  # 禁用流式响应
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
            "max_tokens": max_tokens,
        }
    else:
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "max_output_tokens": max_tokens,
        }
    return base_url, payload, headers


def _should_use_proxy(provider: dict[str, Any], url: str) -> bool:
    if "useProxy" in provider:
        return bool(provider.get("useProxy"))
    return url.startswith("https://")


def _call_provider(provider: dict[str, Any], system_prompt: str, user_prompt: str) -> str:
    api_key = _text(provider.get("apiKey") or provider.get("key"))
    if not api_key:
        raise ValueError("AI 路由缺少 API Key")
    url, payload, headers = _build_request(
        provider,
        system_prompt,
        user_prompt,
        max_tokens=_max_output_tokens(provider),
    )
    if _text(provider.get("apiKeyPlacement") or "header") == "body":
        payload["api_key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"
    timeout = float(provider.get("timeoutSeconds") or 180)
    proxy = (config.HTTPS_PROXY or config.HTTP_PROXY) if _should_use_proxy(provider, url) else None
    proxies = {"http": proxy, "https": proxy} if proxy else None
    response = requests.post(url, headers=headers, json=payload, timeout=timeout, proxies=proxies)
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        public_host = urlparse(config.PUBLIC_BASE_URL).netloc
        route_host = urlparse(url).netloc
        if public_host and route_host == public_host:
            raise RuntimeError(
                f"{response.status_code}: AI 路由地址返回了 FinVue 站点 HTML 页面。"
                "当前模型 Base URL 可能配置成了本应用域名，请改为真实模型网关地址。"
            )
        raise RuntimeError(
            f"{response.status_code}: AI 路由地址返回 HTML 页面，可能不是有效模型接口。"
            "如果填写的是 OpenAI 兼容 Base URL，请选择 OpenAI 格式，系统会自动补齐 /chat/completions。"
        )
    if response.status_code >= 400:
        error_detail = response.text[:500]
        # 尝试解析 JSON 错误信息
        try:
            error_json = response.json()
            if error_json.get("error"):
                error_detail = error_json.get("error", {}).get("message", error_detail)
            elif error_json.get("message"):
                error_detail = error_json.get("message")
        except Exception:
            pass
        # 提供更详细的错误提示
        hint = ""
        if response.status_code == 404:
            hint = "（请检查：1. 模型名称是否正确，如 deepseek-chat；2. 上游地址是否完整，如 https://api.deepseek.com/v1/chat/completions）"
        elif response.status_code == 401:
            hint = "（请检查 API Key 是否正确）"
        elif response.status_code == 403:
            hint = "（请检查 API Key 是否有权限或余额是否充足）"

        raise RuntimeError(f"{response.status_code}: {error_detail}{hint}")

    # 尝试解析响应
    response_text = response.text

    # 检查是否是 SSE 流式响应
    if response_text.startswith("event:") or "data:" in response_text[:100]:
        # 尝试解析 SSE 流式响应，取最后一个有效 data
        text = ""
        content_blocks = {}  # 存储每个 content_block 的文本
        for line in response_text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                continue  # 跳过 event 类型行
            if line.startswith("data:"):
                data_content = line[5:].strip()
                if data_content and data_content != "[DONE]":
                    try:
                        data = json.loads(data_content)
                        # 尝试从流式响应中提取文本
                        if isinstance(data, dict):
                            # Anthropic 格式 - 多种事件类型
                            event_type = data.get("type", "")
                            
                            # content_block_start: 记录 block index 和类型
                            if event_type == "content_block_start":
                                block = data.get("content_block", {})
                                block_index = data.get("index", 0)
                                if block.get("type") == "text":
                                    content_blocks[block_index] = ""
                            
                            # content_block_delta: 提取文本增量
                            elif event_type == "content_block_delta":
                                block_index = data.get("index", 0)
                                delta = data.get("delta", {})
                                if delta.get("type") == "text_delta":
                                    text_delta = delta.get("text", "")
                                    if block_index in content_blocks:
                                        content_blocks[block_index] += text_delta
                                    else:
                                        content_blocks[block_index] = text_delta
                                    text += text_delta
                            
                            # message_delta: 消息状态更新（不包含文本）
                            elif event_type == "message_delta":
                                pass
                            
                            # message_start: 消息开始（不包含文本）
                            elif event_type == "message_start":
                                pass
                            
                            # OpenAI 格式
                            elif data.get("choices"):
                                choice = data["choices"][0]
                                if choice.get("delta"):
                                    text += choice["delta"].get("content", "")
                    except Exception:
                        pass
        
        # 如果增量方式没提取到文本，尝试从 content_blocks 合成
        if not text and content_blocks:
            text = "".join(content_blocks.get(i, "") for i in sorted(content_blocks.keys()))
        
        if not text:
            raise RuntimeError(f"AI 响应解析失败：收到流式响应但无法提取文本，内容：{response_text[:500]}")
    else:
        # 普通 JSON 响应
        try:
            response_data = response.json()
        except Exception as exc:
            raise RuntimeError(f"AI 响应解析失败：{response.status_code} - {response.text[:200]}（{exc}）")

        text = _extract_text(response_data)
    if not text:
        raise RuntimeError("模型返回为空")
    return text


def _routes_from_payload(payload: dict[str, Any], settings: dict[str, Any]) -> list[dict[str, Any]]:
    routes = []
    timeout_override = payload.get("timeoutSeconds")
    
    # 检查 payload 中的 model 是否是提供商 ID
    model_param = payload.get("model", "")
    if model_param:
        # 从 settings 中查找匹配的提供商
        for route in settings.get("aiProviders") or []:
            if isinstance(route, dict) and route.get("id") == model_param:
                if route.get("enabled", True):
                    routes.append({**route, "timeoutSeconds": timeout_override} if timeout_override else route)
                    break
    
    # 如果没有找到匹配的提供商，检查 inline 配置
    if not routes:
        inline = {
            "id": "request-inline",
            "label": payload.get("routeLabel") or "本次请求路由",
            "baseUrl": payload.get("baseUrl") or payload.get("apiBaseUrl"),
            "apiKey": payload.get("apiKey"),
            "model": payload.get("model"),
            "apiFormat": payload.get("apiFormat") or payload.get("format") or "finvue",
            "apiKeyPlacement": payload.get("apiKeyPlacement") or "header",
            "useProxy": payload.get("useProxy", True),
            "enabled": bool(payload.get("apiKey") and payload.get("model") and not model_param.startswith("provider-")),
            "priority": 0,
            "timeoutSeconds": timeout_override,
        }
        if inline["enabled"]:
            routes.append(inline)
    
    # 添加所有启用的提供商作为备用（如果指定了提供商，则不再添加备用）
    if not routes:
        for route in settings.get("aiProviders") or []:
            if isinstance(route, dict) and route.get("enabled", True):
                routes.append({**route, "timeoutSeconds": timeout_override} if timeout_override else route)
    
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
