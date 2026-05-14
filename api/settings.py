from __future__ import annotations

from fastapi import APIRouter, Depends, Request

import security
import store


router = APIRouter()


def _mask_settings(settings: dict) -> dict:
    def mask_provider(provider: dict) -> dict:
        item = {**provider}
        if item.get("apiKey"):
            item["apiKey"] = "********"
            item["hasApiKey"] = True
        return item

    masked = []
    for provider in settings.get("aiProviders") or []:
        if isinstance(provider, dict):
            masked.append(mask_provider(provider))
    defaults = {**store.DEFAULT_SETTINGS, "aiProviders": [mask_provider(item) for item in store.DEFAULT_SETTINGS.get("aiProviders") or [] if isinstance(item, dict)]}
    return {**settings, "aiProviders": masked, "defaults": defaults}


# ============================================
# 提示词预设 API
# ============================================

@router.get("/api/prompts")
def get_prompts() -> dict:
    """获取所有可用的提示词预设列表."""
    prompts = store.get_available_prompts()
    return {"ok": True, "prompts": prompts}


@router.get("/api/prompts/{prompt_id}")
def get_prompt_content(prompt_id: str) -> dict:
    """获取指定提示词的完整内容."""
    prompt_data = store.get_prompt_by_id(prompt_id)
    if not prompt_data:
        return {"ok": False, "error": "提示词不存在"}
    return {"ok": True, "prompt": prompt_data}


@router.put("/api/settings/prompt")
async def set_prompt_preset(request: Request, session: dict = Depends(security.require_auth)) -> dict:
    """切换提示词预设."""
    body = await request.json()
    preset_id = body.get("presetId")
    
    if preset_id == "custom":
        # 使用自定义提示词，保存用户提供的 systemPrompt
        system_prompt = body.get("systemPrompt", "")
        saved = store.save_settings({
            "promptPreset": "custom",
            "systemPrompt": system_prompt,
        })
    elif preset_id in store.PROMPT_PRESETS:
        # 使用预设提示词
        saved = store.save_settings({"promptPreset": preset_id})
    else:
        return {"ok": False, "error": "无效的提示词预设"}
    
    settings = store.get_settings()
    masked = _mask_settings(settings)
    return {"ok": True, "settings": masked}


# ============================================
# 设置 API
# ============================================

@router.get("/api/settings")
def get_settings(session: dict = Depends(security.require_auth)) -> dict:
    settings = store.get_settings() if session.get("role") == "admin" else store.get_effective_settings(session.get("username"))
    masked = _mask_settings(settings)
    return {**masked, "settings": masked}


@router.put("/api/settings")
async def put_settings(request: Request, session: dict = Depends(security.require_any_permission("admin-api"))) -> dict:
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    if session.get("role") != "admin":
        current = store.get_user_ai_settings(session.get("username", ""))
        current_by_id = {p.get("id"): p for p in current.get("aiProviders") or [] if isinstance(p, dict)}
        providers = []
        for provider in incoming.get("aiProviders") or []:
            if not isinstance(provider, dict):
                continue
            existing = current_by_id.get(provider.get("id")) or {}
            item = {**existing, **provider}
            if item.get("apiKey") == "********":
                item["apiKey"] = existing.get("apiKey", "")
            providers.append(item)
        saved = store.save_user_ai_settings(session.get("username", ""), {"aiProviders": providers})
        settings = store.get_effective_settings(session.get("username"))
        masked = _mask_settings(settings)
        return {**masked, "settings": masked, "userAiSettings": saved}

    current = store.get_settings()
    providers = []
    current_by_id = {p.get("id"): p for p in current.get("aiProviders") or [] if isinstance(p, dict)}
    for provider in incoming.get("aiProviders") or []:
        if not isinstance(provider, dict):
            continue
        existing = current_by_id.get(provider.get("id")) or {}
        item = {**existing, **provider}
        if item.get("apiKey") == "********":
            item["apiKey"] = existing.get("apiKey", "")
        providers.append(item)
    if providers:
        incoming["aiProviders"] = providers
    saved = store.save_settings(incoming)
    masked = _mask_settings(saved)
    return {**masked, "settings": masked}
