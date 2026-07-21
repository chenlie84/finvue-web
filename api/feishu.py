from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

import security
from services import feishu_push


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


def _normalize_imported_feishu_settings(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("feishu") if isinstance(raw.get("feishu"), dict) else raw
    settings = data.get("settings") if isinstance(data.get("settings"), dict) else data
    return {
        "enabled": _truthy(_pick(settings, "enabled", "schedulerEnabled", "FEISHU_ENABLED", "FEISHU_PUSH_ENABLED"), True),
        "webhookUrl": str(_pick(settings, "webhookUrl", "webhook", "FEISHU_WEBHOOK_URL", "FEISHU_WEBHOOK") or "").strip(),
        "dailyPushTime": str(_pick(settings, "dailyPushTime", "pushTime", "FEISHU_DAILY_PUSH_TIME", "FEISHU_PUSH_TIME") or "09:00").strip(),
        "pushRelatedStocks": _truthy(_pick(settings, "pushRelatedStocks", "FEISHU_PUSH_RELATED_STOCKS"), True),
        "notifyRegistrations": _truthy(_pick(settings, "notifyRegistrations", "FEISHU_NOTIFY_REGISTRATIONS"), True),
    }


def _parse_uploaded_feishu_config(content: bytes, filename: str = "") -> dict[str, Any]:
    text = content.decode("utf-8-sig").strip()
    if not text:
        raise ValueError("配置文件为空")
    if filename.lower().endswith(".json") or text[:1] in {"{", "["}:
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ValueError("JSON 配置顶层必须是对象")
        return _normalize_imported_feishu_settings(loaded)
    return _normalize_imported_feishu_settings(_parse_env_config(text))


@router.get("/api/admin/feishu")
def get_feishu_settings(_: dict = Depends(security.require_admin)) -> dict:
    return {"ok": True, "settings": feishu_push.mask_settings()}


@router.put("/api/admin/feishu")
async def put_feishu_settings(request: Request, session: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    saved = feishu_push.save_settings(incoming if isinstance(incoming, dict) else {}, session.get("username", ""))
    return {"ok": True, "settings": feishu_push.mask_settings(saved)}


@router.get("/api/admin/feishu/export")
def export_feishu_settings(_: dict = Depends(security.require_admin)) -> Response:
    settings = feishu_push.get_settings()
    payload = {
        "type": "finvue-feishu-config",
        "version": 1,
        "exportedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feishu": {
            "enabled": settings.get("enabled"),
            "webhookUrl": settings.get("webhookUrl"),
            "dailyPushTime": settings.get("dailyPushTime"),
            "pushRelatedStocks": settings.get("pushRelatedStocks"),
            "notifyRegistrations": settings.get("notifyRegistrations"),
        },
    }
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="finvue-feishu-config.json"'},
    )


@router.get("/api/admin/feishu/template")
def export_feishu_template(_: dict = Depends(security.require_admin)) -> Response:
    payload = {
        "type": "finvue-feishu-config",
        "version": 1,
        "feishu": {
            "enabled": True,
            "webhookUrl": "https://open.feishu.cn/open-apis/bot/v2/hook/...",
            "dailyPushTime": "09:00",
            "pushRelatedStocks": True,
            "notifyRegistrations": True,
        },
    }
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="finvue-feishu-config-template.json"'},
    )


@router.post("/api/admin/feishu/import")
async def import_feishu_settings(
    file: UploadFile = File(...),
    session: dict = Depends(security.require_admin),
) -> dict:
    content = await file.read()
    try:
        settings = _parse_uploaded_feishu_config(content, file.filename or "")
        current = feishu_push.get_settings()
        webhook = str(settings.get("webhookUrl") or "").strip()
        if not webhook or webhook == "********" or webhook.endswith("/..."):
            settings["webhookUrl"] = current.get("webhookUrl", "")
        saved = feishu_push.save_settings(settings, session.get("username", ""))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"飞书配置文件导入失败：{exc}") from exc
    return {
        "ok": True,
        "message": "飞书配置已导入并保存",
        "settings": feishu_push.mask_settings(saved),
        "imported": {
            "enabled": bool(saved.get("enabled")),
            "hasWebhook": bool(saved.get("webhookUrl")),
            "dailyPushTime": saved.get("dailyPushTime"),
            "pushRelatedStocks": saved.get("pushRelatedStocks"),
            "notifyRegistrations": saved.get("notifyRegistrations"),
        },
    }


@router.post("/api/admin/feishu/test")
async def test_feishu_push(_: Request, __: dict = Depends(security.require_admin)) -> dict:
    try:
        result = await asyncio.to_thread(feishu_push.push_now)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"飞书推送失败：{exc}") from exc
    return {"ok": True, "message": result.get("message", "推送成功")}
