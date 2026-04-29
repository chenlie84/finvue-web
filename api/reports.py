from __future__ import annotations

from fastapi import APIRouter, Depends, Request

import security
import store


router = APIRouter()


@router.get("/api/reports")
def get_reports(page: int = 1, pageSize: int = 20, q: str = "", anchorName: str = "", _: dict = Depends(security.require_permission("export"))) -> dict:
    return store.get_reports(page, pageSize, q, anchorName)


@router.post("/api/reports")
async def post_report(request: Request, _: dict = Depends(security.require_permission("export"))) -> dict:
    report = store.save_report(await request.json())
    return {"ok": True, "report": report}
