from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

import ai_router
import config
import security
import store
from services import pdf_export
from services import object_storage


router = APIRouter()


# ══════════════ 兼容 API 端点 ══════════════

@router.post("/v1/chat/completions")
async def openai_compatible_chat(request: Request) -> Dict[str, Any]:
    """OpenAI 兼容的 Chat Completions API"""
    body = await request.json()

    # 提取 messages
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    # 提取 system prompt
    system_prompt = ""
    filtered_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_prompt = content
        else:
            filtered_messages.append(msg)

    # 合并 user messages 为 user_prompt
    user_prompt = "\n".join(str(msg.get("content", "")) for msg in filtered_messages if msg.get("role") == "user")

    # 构建 FinVue 格式的 payload
    payload = {
        "systemPrompt": system_prompt,
        "userPrompt": user_prompt,
        "model": body.get("model", ""),
    }

    # 检查是否有内联 API Key
    if body.get("apiKey"):
        payload["apiKey"] = body.get("apiKey")
    if body.get("baseUrl"):
        payload["baseUrl"] = body.get("baseUrl")

    try:
        result = ai_router.generate(payload)
        return {
            "id": f"chatcmpl-{hash(user_prompt) % 1000000}",
            "object": "chat.completion",
            "created": int(__import__("time").time()),
            "model": body.get("model", "unknown"),
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result.get("markdown", "")
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(system_prompt + user_prompt) // 4,
                "completion_tokens": len(result.get("markdown", "")) // 4,
                "total_tokens": (len(system_prompt + user_prompt) + len(result.get("markdown", ""))) // 4
            }
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/v1/messages")
async def anthropic_compatible_messages(request: Request) -> Dict[str, Any]:
    """Anthropic 兼容的 Messages API"""
    body = await request.json()

    # 提取 model
    model = body.get("model", "claude-sonnet-4-20250514")

    # 提取 system prompt
    system_prompt = body.get("system", "")

    # 提取 messages
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")

    # 构建 user prompt（Anthropic 格式：消息可能是 content 数组）
    user_prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # 处理多模态内容（简化处理，只取 text）
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    user_prompt_parts.append(str(item.get("text", "")))
        else:
            user_prompt_parts.append(str(content))

    user_prompt = "\n".join(user_prompt_parts)

    # 构建 FinVue 格式的 payload
    payload = {
        "systemPrompt": system_prompt,
        "userPrompt": user_prompt,
        "model": model,
    }

    # 检查是否有内联 API Key
    if body.get("api_key"):
        payload["apiKey"] = body.get("api_key")
    if body.get("base_url"):
        payload["baseUrl"] = body.get("base_url")

    # Anthropic 需要 max_tokens
    max_tokens = body.get("max_tokens", 4096)

    try:
        result = ai_router.generate(payload)
        markdown = result.get("markdown", "")

        return {
            "id": f"msg_{hash(user_prompt) % 1000000}",
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "text",
                    "text": markdown
                }
            ],
            "model": model,
            "stop_reason": "end_turn",
            "usage": {
                "input_tokens": len(system_prompt + user_prompt) // 4,
                "output_tokens": len(markdown) // 4
            }
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ══════════════ 测试 AI 路由接口 ══════════════

@router.post("/api/test-ai-provider")
async def test_ai_provider(request: Request, session: dict = Depends(security.require_permission("live"))) -> Dict[str, Any]:
    """测试 AI 路由连接"""
    body = await request.json()

    # 提取配置
    base_url = body.get("baseUrl", "").strip()
    api_key = body.get("apiKey", "").strip()
    model = body.get("model", "").strip()
    api_format = body.get("apiFormat", "finvue")
    api_key_placement = body.get("apiKeyPlacement", "header")
    use_proxy = body.get("useProxy", True)

    if not base_url:
        return {"success": False, "error": "请填写上游地址"}
    if not api_key:
        return {"success": False, "error": "请填写 API Key"}
    if not model:
        return {"success": False, "error": "请填写模型名"}

    # 构造测试请求
    headers = {"Content-Type": "application/json"}
    test_prompt = "你好，请回复" + "。" if api_format == "anthropic" else ""

    if api_format == "anthropic" or "/v1/messages" in base_url:
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": model,
            "max_tokens": 50,
            "messages": [{"role": "user", "content": test_prompt}],
        }
    elif api_format == "openai" or "/chat/completions" in base_url:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "你是助手"},
                {"role": "user", "content": test_prompt}
            ],
            "stream": False,
        }
    else:
        # FinVue 格式
        payload = {
            "model": model,
            "input": [
                {"role": "user", "content": test_prompt}
            ],
            "stream": False,
        }

    if api_key_placement == "body":
        payload["api_key"] = api_key
    else:
        headers["Authorization"] = f"Bearer {api_key}"

    # 发送测试请求
    import requests as req
    proxy = None
    if use_proxy:
        import config
        proxy = config.HTTPS_PROXY or config.HTTP_PROXY
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        response = req.post(base_url, headers=headers, json=payload, timeout=30, proxies=proxies)

        if response.status_code >= 400:
            # 尝试解析错误信息
            try:
                error_data = response.json()
                error_msg = error_data.get("error", {}).get("message") or error_data.get("message") or response.text[:200]
            except Exception:
                error_msg = response.text[:200]

            hint = ""
            if response.status_code == 401:
                hint = "（API Key 可能不正确）"
            elif response.status_code == 403:
                hint = "（API Key 无权限或余额不足）"
            elif response.status_code == 404:
                hint = "（请检查上游地址和模型名称）"

            return {"success": False, "error": f"{response.status_code}: {error_msg}{hint}"}

        # 尝试解析响应
        try:
            data = response.json()
            # 检查是否有有效内容
            if api_format == "anthropic" or "/v1/messages" in base_url:
                if isinstance(data.get("content"), list) and data["content"]:
                    return {"success": True, "message": "连接成功"}
            elif api_format == "openai" or "/chat/completions" in base_url:
                if data.get("choices"):
                    return {"success": True, "message": "连接成功"}
            elif data.get("output_text") or data.get("output"):
                return {"success": True, "message": "连接成功"}
        except Exception:
            pass

        return {"success": False, "error": "响应格式异常"}

    except req.exceptions.Timeout:
        return {"success": False, "error": "请求超时"}
    except req.exceptions.ConnectionError:
        return {"success": False, "error": "连接失败，请检查网络或代理设置"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.post("/api/generate")
async def generate(request: Request, session: dict = Depends(security.require_permission("live"))) -> dict:
    body = await request.json()
    return ai_router.generate(body, username=session.get("username"))


@router.post("/api/generate-stream")
async def generate_stream(request: Request, session: dict = Depends(security.require_permission("live"))) -> StreamingResponse:
    body = await request.json()

    def events():
        yield json.dumps({"type": "status", "message": "已接收任务，正在调用 AI 路由"}, ensure_ascii=False) + "\n"
        try:
            result = ai_router.generate(body, username=session.get("username"))
            markdown = result.get("markdown") or ""
            for index in range(0, len(markdown), 1200):
                yield json.dumps({"type": "chunk", "content": markdown[index : index + 1200]}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "done", **result}, ensure_ascii=False) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson; charset=utf-8")


@router.post("/api/analysis-persist")
async def persist_analysis(request: Request, session: dict = Depends(security.require_permission("live"))) -> dict:
    body = await request.json()
    return store.persist_analysis_bundle(body, created_by=str(session.get("username") or ""))


@router.post("/api/export-plugin")
async def export_plugin(request: Request, _: dict = Depends(security.require_permission("export"))) -> dict:
    body = await request.json()
    return {"ok": True, "content": body}


@router.post("/api/export-report-pdf")
async def export_report_pdf(request: Request, _: dict = Depends(security.require_any_permission("live", "export"))) -> StreamingResponse:
    body = await request.json()
    file_name = pdf_export.safe_pdf_filename(str(body.get("fileName") or body.get("filename") or "finvue-report"))
    try:
        data = pdf_export.render_pdf_bytes(str(body.get("html") or ""))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    headers = {"Content-Disposition": f'attachment; filename="{file_name}.pdf"'}
    if config.has_ceph_config():
        try:
            uploaded = object_storage.upload_bytes(data, file_name=f"{file_name}.pdf", prefix=config.CEPH_KEY_PREFIX, content_type="application/pdf")
            headers["X-FinVue-S3-Key"] = uploaded.get("key", "")
            headers["X-FinVue-S3-Url"] = uploaded.get("url", "")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF 已生成，但上传 S3 失败：{exc}") from exc
    return StreamingResponse(
        iter([data]),
        media_type="application/pdf",
        headers=headers,
    )


@router.post("/api/extract-pdf")
async def extract_pdf(_: Request, __: dict = Depends(security.require_permission("live"))) -> dict:
    return {"ok": False, "error": "服务端 PDF 文本提取未启用；页面会自动尝试浏览器端读取。若仍失败，请上传 txt/docx。"}
