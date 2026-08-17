from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

import security
import store
from api import feishu as feishu_api
from api import market as market_api
from services import daily_review_scheduler, feishu_push, tushare_market


router = APIRouter()


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "启用", "是"}


def _parse_env_config(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _pick(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    return None


def _looks_like_placeholder_key(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    return text == "********" or "your-" in lowered or "填入" in text or text.endswith("...")


def _normalize_ai_provider(raw: dict[str, Any], index: int = 0, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    existing = existing or {}
    provider_id = str(_pick(raw, "id", "providerId", "AI_PROVIDER_ID") or existing.get("id") or f"provider-{index + 1}").strip()
    api_key = str(_pick(raw, "apiKey", "key", "AI_API_KEY", "AI_PROVIDER_API_KEY") or "").strip()
    if _looks_like_placeholder_key(api_key):
        api_key = str(existing.get("apiKey") or "").strip()
    priority_raw = _pick(raw, "priority", "AI_PRIORITY")
    timeout_raw = _pick(raw, "timeoutSeconds", "AI_TIMEOUT_SECONDS")
    max_output_tokens_raw = _pick(raw, "maxOutputTokens", "max_output_tokens", "maxTokens", "AI_MAX_OUTPUT_TOKENS")
    item = {
        "id": provider_id,
        "label": str(_pick(raw, "label", "name", "AI_PROVIDER_LABEL") or existing.get("label") or f"路由 {index + 1}").strip(),
        "baseUrl": str(_pick(raw, "baseUrl", "url", "AI_BASE_URL", "AI_PROVIDER_BASE_URL") or existing.get("baseUrl") or "https://ark.cn-beijing.volces.com/api/v3/responses").strip(),
        "apiKey": api_key,
        "model": str(_pick(raw, "model", "AI_MODEL", "AI_PROVIDER_MODEL") or existing.get("model") or "").strip(),
        "enabled": _truthy(_pick(raw, "enabled", "AI_ENABLED"), bool(existing.get("enabled", True))),
        "priority": int(float(priority_raw)) if priority_raw not in (None, "") else int(existing.get("priority") or index + 1),
        "apiFormat": str(_pick(raw, "apiFormat", "format", "AI_API_FORMAT") or existing.get("apiFormat") or "finvue").strip(),
        "apiKeyPlacement": str(_pick(raw, "apiKeyPlacement", "keyPlacement", "AI_API_KEY_PLACEMENT") or existing.get("apiKeyPlacement") or "header").strip(),
        "useProxy": _truthy(_pick(raw, "useProxy", "AI_USE_PROXY"), bool(existing.get("useProxy", True))),
    }
    if max_output_tokens_raw not in (None, ""):
        try:
            item["maxOutputTokens"] = max(1024, min(int(float(max_output_tokens_raw)), 32768))
        except (TypeError, ValueError):
            item["maxOutputTokens"] = int(existing.get("maxOutputTokens") or 8192)
    else:
        item["maxOutputTokens"] = int(existing.get("maxOutputTokens") or 8192)
    if timeout_raw not in (None, ""):
        item["timeoutSeconds"] = int(float(timeout_raw))
    elif existing.get("timeoutSeconds") not in (None, ""):
        item["timeoutSeconds"] = existing.get("timeoutSeconds")
    return item


def _normalize_imported_ai_settings(raw: dict[str, Any], existing_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    existing_by_id = existing_by_id or {}
    data = raw.get("settings") if isinstance(raw.get("settings"), dict) else raw
    ai_block = data.get("ai") if isinstance(data.get("ai"), dict) else data
    providers = (
        ai_block.get("providers")
        if isinstance(ai_block.get("providers"), list)
        else ai_block.get("aiProviders")
        if isinstance(ai_block.get("aiProviders"), list)
        else data.get("aiProviders")
        if isinstance(data.get("aiProviders"), list)
        else None
    )
    if providers is None and isinstance(data.get("aiProvider"), dict):
        providers = [data.get("aiProvider")]
    if providers is None and any(key in data for key in ("AI_API_KEY", "AI_PROVIDER_API_KEY", "baseUrl", "apiKey", "model")):
        providers = [data]
    if not providers:
        raise ValueError("未找到 ai.providers / aiProviders 配置")
    normalized = []
    for index, provider in enumerate(providers):
        if not isinstance(provider, dict):
            continue
        provider_id = str(_pick(provider, "id", "providerId", "AI_PROVIDER_ID") or "").strip()
        existing = existing_by_id.get(provider_id, {}) if provider_id else {}
        normalized.append(_normalize_ai_provider(provider, index, existing))
    if not normalized:
        raise ValueError("AI 路由配置为空")
    return {"aiProviders": normalized}


def _parse_uploaded_ai_config(content: bytes, filename: str = "", existing_by_id: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    text = content.decode("utf-8-sig").strip()
    if not text:
        raise ValueError("配置文件为空")
    if filename.lower().endswith(".json") or text[:1] in {"{", "["}:
        loaded = json.loads(text)
        if isinstance(loaded, list):
            loaded = {"aiProviders": loaded}
        if not isinstance(loaded, dict):
            raise ValueError("JSON 配置顶层必须是对象或数组")
        return _normalize_imported_ai_settings(loaded, existing_by_id)
    return _normalize_imported_ai_settings(_parse_env_config(text), existing_by_id)


def _has_any_key(data: dict[str, Any], *keys: str) -> bool:
    return any(key in data for key in keys)


def _current_config_bundle() -> dict[str, Any]:
    settings = store.get_settings()
    tushare = tushare_market.get_settings()
    feishu = feishu_push.get_settings()
    daily_review = daily_review_scheduler.get_settings()
    return {
        "type": "finvue-config-bundle",
        "version": 1,
        "exportedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tushare": {
            "enabled": tushare.get("enabled"),
            "token": tushare.get("token"),
            "intervalMinutes": tushare.get("intervalMinutes"),
            "indexCodes": tushare.get("indexCodes"),
            "stockCodes": tushare.get("stockCodes"),
        },
        "feishu": {
            "enabled": feishu.get("enabled"),
            "webhookUrl": feishu.get("webhookUrl"),
            "dailyPushTime": feishu.get("dailyPushTime"),
            "pushRelatedStocks": feishu.get("pushRelatedStocks"),
            "notifyRegistrations": feishu.get("notifyRegistrations"),
        },
        "ai": {
            "providers": settings.get("aiProviders") or [],
        },
        "dailyReview": {
            "scheduler": {
                "enabled": daily_review.get("enabled"),
                "dailyRunTime": daily_review.get("dailyRunTime"),
                "retryMinutes": daily_review.get("retryMinutes"),
                "weekdayOnly": daily_review.get("weekdayOnly"),
            },
        },
    }


def _config_bundle_template() -> dict[str, Any]:
    return {
        "type": "finvue-config-bundle",
        "version": 1,
        "tushare": {
            "enabled": True,
            "token": "填入你的 TuShare Token",
            "intervalMinutes": 60,
            "indexCodes": tushare_market.DEFAULT_INDEX_CODES,
            "stockCodes": tushare_market.DEFAULT_STOCK_CODES,
        },
        "feishu": {
            "enabled": True,
            "webhookUrl": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
            "dailyPushTime": "09:00",
            "pushRelatedStocks": True,
            "notifyRegistrations": True,
        },
        "ai": {
            "providers": [
                {
                    "id": "primary-volcengine",
                    "label": "火山主路由",
                    "baseUrl": "https://ark.cn-beijing.volces.com/api/v3/responses",
                    "apiKey": "填入你的 AI API Key",
                    "model": "doubao-seed-2-0-pro-250415",
                    "enabled": True,
                    "priority": 20,
                    "apiFormat": "finvue",
                    "apiKeyPlacement": "header",
                    "useProxy": True,
                    "maxOutputTokens": 8192,
                }
            ],
        },
        "dailyReview": {
            "scheduler": {
                "enabled": True,
                "dailyRunTime": "17:40",
                "retryMinutes": 30,
                "weekdayOnly": True,
            },
        },
    }


def _parse_uploaded_config_bundle(
    content: bytes,
    filename: str = "",
    existing_ai_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    text = content.decode("utf-8-sig").strip()
    if not text:
        raise ValueError("配置文件为空")
    if filename.lower().endswith(".json") or text[:1] == "{":
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ValueError("JSON 配置顶层必须是对象")
        data = loaded.get("finvue") if isinstance(loaded.get("finvue"), dict) else loaded
    else:
        data = _parse_env_config(text)

    if existing_ai_by_id is None:
        current_ai = store.get_settings()
        existing_ai_by_id = {p.get("id"): p for p in current_ai.get("aiProviders") or [] if isinstance(p, dict) and p.get("id")}
    parsed: dict[str, Any] = {}

    if isinstance(data.get("tushare"), dict) or _has_any_key(data, "TUSHARE_TOKEN", "TUSHARE_API_TOKEN", "TUSHARE_ENABLED", "TUSHARE_INDEX_CODES", "TUSHARE_STOCK_CODES"):
        parsed["tushare"] = market_api._normalize_imported_tushare_settings(data)
    if isinstance(data.get("feishu"), dict) or _has_any_key(data, "FEISHU_WEBHOOK_URL", "FEISHU_WEBHOOK", "FEISHU_ENABLED", "FEISHU_PUSH_ENABLED", "FEISHU_DAILY_PUSH_TIME"):
        parsed["feishu"] = feishu_api._normalize_imported_feishu_settings(data)
    if isinstance(data.get("ai"), dict) or isinstance(data.get("aiProviders"), list) or _has_any_key(data, "AI_API_KEY", "AI_PROVIDER_API_KEY", "AI_BASE_URL", "AI_MODEL"):
        parsed["ai"] = _normalize_imported_ai_settings(data, existing_ai_by_id)
    daily_review = data.get("dailyReview") if isinstance(data.get("dailyReview"), dict) else {}
    scheduler = daily_review.get("scheduler") if isinstance(daily_review.get("scheduler"), dict) else {}
    if scheduler or _has_any_key(data, "DAILY_REVIEW_SCHEDULER_ENABLED", "DAILY_REVIEW_RUN_TIME", "DAILY_REVIEW_RETRY_MINUTES", "DAILY_REVIEW_WEEKDAY_ONLY"):
        parsed["dailyReview"] = {
            "scheduler": {
                "enabled": _truthy(_pick(scheduler or data, "enabled", "DAILY_REVIEW_SCHEDULER_ENABLED"), True),
                "dailyRunTime": str(_pick(scheduler or data, "dailyRunTime", "runTime", "DAILY_REVIEW_RUN_TIME") or "17:40").strip(),
                "retryMinutes": _pick(scheduler or data, "retryMinutes", "DAILY_REVIEW_RETRY_MINUTES") or 30,
                "weekdayOnly": _truthy(_pick(scheduler or data, "weekdayOnly", "DAILY_REVIEW_WEEKDAY_ONLY"), True),
            }
        }

    if not parsed:
        raise ValueError("未找到可导入的 tushare / feishu / ai 配置段")
    return parsed


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


@router.get("/api/admin/config/export")
def export_config_bundle(_: dict = Depends(security.require_admin)) -> Response:
    return Response(
        json.dumps(_current_config_bundle(), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="finvue-config-bundle.json"'},
    )


@router.get("/api/admin/config/template")
def export_config_bundle_template(_: dict = Depends(security.require_admin)) -> Response:
    return Response(
        json.dumps(_config_bundle_template(), ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="finvue-config-bundle-template.json"'},
    )


@router.post("/api/admin/config/import")
async def import_config_bundle(
    file: UploadFile = File(...),
    session: dict = Depends(security.require_admin),
) -> dict:
    content = await file.read()
    try:
        current_ai = store.get_settings()
        existing_ai_by_id = {p.get("id"): p for p in current_ai.get("aiProviders") or [] if isinstance(p, dict) and p.get("id")}
        parsed = _parse_uploaded_config_bundle(content, file.filename or "", existing_ai_by_id)
        imported: dict[str, Any] = {}
        if "tushare" in parsed:
            settings = parsed["tushare"]
            current = tushare_market.get_settings()
            token = str(settings.get("token") or "").strip()
            if _looks_like_placeholder_key(token) or token.startswith("填入"):
                settings["token"] = current.get("token", "")
            saved = tushare_market.save_settings(settings, session.get("username", ""))
            imported["tushare"] = {
                "enabled": bool(saved.get("enabled")),
                "hasToken": bool(saved.get("token")),
                "indexCount": len(saved.get("indexCodes") or []),
                "stockCount": len(saved.get("stockCodes") or []),
            }
        if "feishu" in parsed:
            settings = parsed["feishu"]
            current = feishu_push.get_settings()
            webhook = str(settings.get("webhookUrl") or "").strip()
            if _looks_like_placeholder_key(webhook) or webhook.endswith("/..."):
                settings["webhookUrl"] = current.get("webhookUrl", "")
            saved = feishu_push.save_settings(settings, session.get("username", ""))
            imported["feishu"] = {
                "enabled": bool(saved.get("enabled")),
                "hasWebhook": bool(saved.get("webhookUrl")),
                "dailyPushTime": saved.get("dailyPushTime"),
            }
        if "ai" in parsed:
            saved = store.save_settings(parsed["ai"])
            providers = [p for p in saved.get("aiProviders") or [] if isinstance(p, dict)]
            imported["ai"] = {
                "providerCount": len(providers),
                "enabledCount": len([p for p in providers if p.get("enabled")]),
                "keyCount": len([p for p in providers if p.get("apiKey")]),
            }
        if "dailyReview" in parsed:
            scheduler = store.safe_object(parsed["dailyReview"].get("scheduler"))
            saved = daily_review_scheduler.save_settings(scheduler, session.get("username", ""))
            imported["dailyReview"] = {
                "schedulerEnabled": bool(saved.get("enabled")),
                "dailyRunTime": saved.get("dailyRunTime"),
                "retryMinutes": saved.get("retryMinutes"),
                "weekdayOnly": saved.get("weekdayOnly"),
            }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"总配置文件导入失败：{exc}") from exc
    masked = _mask_settings(store.get_settings())
    return {
        "ok": True,
        "message": "FinVue 总配置已导入并保存",
        "settings": masked,
        "imported": imported,
    }


@router.get("/api/admin/ai-config/export")
def export_ai_config(_: dict = Depends(security.require_admin)) -> Response:
    settings = store.get_settings()
    payload = {
        "type": "finvue-ai-config",
        "version": 1,
        "exportedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ai": {
            "providers": settings.get("aiProviders") or [],
        },
    }
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="finvue-ai-config.json"'},
    )


@router.get("/api/admin/ai-config/template")
def export_ai_config_template(_: dict = Depends(security.require_admin)) -> Response:
    payload = {
        "type": "finvue-ai-config",
        "version": 1,
        "ai": {
            "providers": [
                {
                    "id": "primary-volcengine",
                    "label": "火山主路由",
                    "baseUrl": "https://ark.cn-beijing.volces.com/api/v3/responses",
                    "apiKey": "填入你的 API Key",
                    "model": "doubao-seed-2-0-pro-250415",
                    "enabled": True,
                    "priority": 20,
                    "apiFormat": "finvue",
                    "apiKeyPlacement": "header",
                    "useProxy": True,
                }
            ],
        },
    }
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="finvue-ai-config-template.json"'},
    )


@router.post("/api/admin/ai-config/import")
async def import_ai_config(
    file: UploadFile = File(...),
    _: dict = Depends(security.require_admin),
) -> dict:
    content = await file.read()
    current = store.get_settings()
    existing_by_id = {p.get("id"): p for p in current.get("aiProviders") or [] if isinstance(p, dict) and p.get("id")}
    try:
        imported = _parse_uploaded_ai_config(content, file.filename or "", existing_by_id)
        saved = store.save_settings(imported)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"AI 配置文件导入失败：{exc}") from exc
    masked = _mask_settings(saved)
    providers = [p for p in saved.get("aiProviders") or [] if isinstance(p, dict)]
    return {
        "ok": True,
        "message": "AI 路由配置已导入并保存",
        "settings": masked,
        "imported": {
            "providerCount": len(providers),
            "enabledCount": len([p for p in providers if p.get("enabled")]),
            "keyCount": len([p for p in providers if p.get("apiKey")]),
        },
    }


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
