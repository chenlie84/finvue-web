from __future__ import annotations

import asyncio
import shutil

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

import security
from services import data_collection


router = APIRouter()


@router.get("/api/data-collection/recent")
def recent(_: dict = Depends(security.require_permission("data-collection"))) -> dict:
    return {"ok": True, "items": data_collection.recent_items(), "root": str(data_collection.ROOT)}


@router.post("/api/data-collection/douyin")
async def collect_douyin(request: Request, _: dict = Depends(security.require_permission("data-collection"))) -> dict:
    body = await request.json()
    source = str(body.get("source") or "").strip()
    if not source:
        raise HTTPException(status_code=400, detail="请输入抖音分享链接或视频 ID")
    try:
        return await asyncio.to_thread(
            data_collection.collect_douyin_video,
            source,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/data-collection/douyin/{aweme_id}/audio")
async def download_audio(aweme_id: str, _: dict = Depends(security.require_permission("data-collection"))) -> FileResponse:
    try:
        audio_path = await asyncio.to_thread(data_collection.build_audio_download, aweme_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return FileResponse(
        audio_path,
        media_type="audio/mp4",
        filename=f"{aweme_id}.audio.m4a",
        background=BackgroundTask(lambda: shutil.rmtree(audio_path.parent, ignore_errors=True)),
    )
