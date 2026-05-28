from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

import security
from services import tushare_market


router = APIRouter()


@router.get("/api/market/overview")
def overview(_: dict = Depends(security.require_permission("market"))) -> dict:
    settings = tushare_market.mask_settings()
    cache = tushare_market.get_cached_snapshot()
    return {"ok": True, "settings": settings, "snapshot": cache}


@router.post("/api/market/refresh")
async def refresh(_: Request, __: dict = Depends(security.require_permission("market"))) -> dict:
    settings = tushare_market.get_settings()
    if not settings.get("token"):
        raise HTTPException(status_code=400, detail="TuShare token 未配置")
    try:
        snapshot = await asyncio.to_thread(tushare_market.fetch_market_snapshot, settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "snapshot": snapshot}


@router.get("/api/admin/tushare")
def get_tushare_settings(_: dict = Depends(security.require_admin)) -> dict:
    return {"ok": True, "settings": tushare_market.mask_settings()}


@router.put("/api/admin/tushare")
async def put_tushare_settings(request: Request, session: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    saved = tushare_market.save_settings(incoming if isinstance(incoming, dict) else {}, session.get("username", ""))
    return {"ok": True, "settings": tushare_market.mask_settings(saved)}


@router.post("/api/admin/tushare/test")
async def test_tushare_settings(request: Request, _: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    incoming = incoming if isinstance(incoming, dict) else {}
    current = tushare_market.get_settings()
    token = str(incoming.get("token") or "")
    if token == "********":
        token = current.get("token", "")
    if not token:
        raise HTTPException(status_code=400, detail="请先填写 TuShare token")
    try:
        result = await asyncio.to_thread(tushare_market.test_token, token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"TuShare 连接失败：{exc}") from exc
    return {"ok": True, "message": f"连接成功，交易日历返回 {result.get('rows', 0)} 条"}
