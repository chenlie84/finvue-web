from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

import security
from services import feishu_push


router = APIRouter()


@router.get("/api/admin/feishu")
def get_feishu_settings(_: dict = Depends(security.require_admin)) -> dict:
    return {"ok": True, "settings": feishu_push.mask_settings()}


@router.put("/api/admin/feishu")
async def put_feishu_settings(request: Request, session: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    saved = feishu_push.save_settings(incoming if isinstance(incoming, dict) else {}, session.get("username", ""))
    return {"ok": True, "settings": feishu_push.mask_settings(saved)}


@router.post("/api/admin/feishu/test")
async def test_feishu_push(_: Request, __: dict = Depends(security.require_admin)) -> dict:
    try:
        result = await asyncio.to_thread(feishu_push.push_now)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"飞书推送失败：{exc}") from exc
    return {"ok": True, "message": result.get("message", "推送成功")}
