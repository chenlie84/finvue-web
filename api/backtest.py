from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

import security
from services import backtest


router = APIRouter()


@router.get("/api/backtest/anchors")
def get_backtest_anchors(_: dict = Depends(security.require_permission("backtest"))) -> dict:
    return backtest.list_anchors()


@router.post("/api/backtest/run")
async def run_backtest(request: Request, _: dict = Depends(security.require_permission("backtest"))) -> dict:
    body = await request.json()
    try:
        return await asyncio.to_thread(backtest.run_backtest, body if isinstance(body, dict) else {})
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"历史回测失败：{exc}") from exc
