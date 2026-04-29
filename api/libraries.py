from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import security
import store


router = APIRouter()


@router.get("/api/anchor-profiles")
def get_anchor_profiles(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", _: dict = Depends(security.require_permission("anchor-library"))) -> dict:
    return store.get_anchor_profiles(page, pageSize, q)


@router.post("/api/anchor-profiles")
async def post_anchor_profiles(request: Request, _: dict = Depends(security.require_permission("anchor-library"))) -> dict:
    return store.save_anchor_profiles(await request.json())


@router.get("/api/anchor-roi-settings")
def get_anchor_roi(_: dict = Depends(security.require_permission("portrait"))) -> dict:
    return store.get_anchor_roi_settings()


@router.put("/api/anchor-roi-settings")
async def put_anchor_roi(request: Request, _: dict = Depends(security.require_permission("portrait"))) -> dict:
    return store.save_anchor_roi_settings(await request.json())


@router.get("/api/compliance-library")
def get_compliance(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", _: dict = Depends(security.require_permission("compliance-library"))) -> dict:
    return store.get_compliance_library(page, pageSize, q)


@router.post("/api/compliance-library")
async def post_compliance(request: Request, _: dict = Depends(security.require_permission("compliance-library"))) -> dict:
    return store.save_compliance_library(await request.json())


@router.get("/api/case-library")
def get_cases(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", _: dict = Depends(security.require_permission("case-library"))) -> dict:
    return store.get_case_library(page, pageSize, q)


@router.post("/api/case-library")
async def post_cases(request: Request, _: dict = Depends(security.require_permission("case-library"))) -> dict:
    return store.save_case_library(await request.json())


@router.get("/api/transcript-library")
def get_transcripts(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", _: dict = Depends(security.require_permission("transcript-library"))) -> dict:
    return store.get_transcript_library(page, pageSize, q)


@router.post("/api/transcript-library")
async def post_transcripts(request: Request, _: dict = Depends(security.require_permission("transcript-library"))) -> dict:
    return store.save_transcript_library(await request.json())


@router.delete("/api/transcript-library")
async def delete_transcript(request: Request, id: str = Query("", alias="id"), _: dict = Depends(security.require_permission("transcript-library"))) -> dict:
    item_id = id
    anchor_name = ""
    if not item_id:
        try:
            body = await request.json()
            item_id = str(body.get("id") or "")
            anchor_name = str(body.get("anchorName") or "")
        except Exception:
            item_id = ""
            anchor_name = ""
    if anchor_name:
        return store.delete_transcripts_by_anchor(anchor_name)
    if not item_id:
        raise HTTPException(status_code=400, detail="缺少逐字稿 id")
    return store.delete_transcript(item_id)


@router.patch("/api/library-identity")
async def patch_identity(request: Request, _: dict = Depends(security.require_any_permission("anchor-library", "transcript-library", "customer-library"))) -> dict:
    body = await request.json()
    old_name = store.text(body.get("oldName") or body.get("from"))
    new_name = store.text(body.get("newName") or body.get("to"))
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="缺少原名称或新名称")
    # 线上版先同步规范化表，finvue_app_kv 中的历史原始 JSON 由后续迁移脚本统一清理。
    store.db.execute("UPDATE finvue_anchor_profiles SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))
    store.db.execute("UPDATE finvue_transcripts SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))
    store.db.execute("UPDATE finvue_analysis_reports SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))
    store.db.execute("UPDATE finvue_customer_profiles SET latest_anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE latest_anchor_name = %s", (new_name, old_name))
    store.db.execute("UPDATE finvue_customer_sessions SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))
    return {"ok": True, "oldName": old_name, "newName": new_name}
