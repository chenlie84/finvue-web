from __future__ import annotations

from fastapi import APIRouter, Depends, Request

import security
import store


router = APIRouter()


@router.get("/api/health")
def health() -> dict:
    return {"ok": True, "runtime": "fastapi", "database": "mysql"}


@router.get("/api/anchor-dashboard/weekly")
def dashboard_weekly(_: dict = Depends(security.require_permission("home"))) -> dict:
    return {"ok": True, "items": [], "message": "FastAPI 线上版已接管，数据看板将通过 MySQL 聚合接口补齐。"}


@router.post("/api/live-room-analytics/sync")
async def sync_once(request: Request, _: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    return store.enqueue_job("douyin_sync", body)


@router.post("/api/live-room-analytics/sync/start")
async def sync_start(request: Request, _: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    job = store.enqueue_job("douyin_sync", body)
    return {"ok": True, "jobId": job["id"], "status": job["status"], "job": job}


@router.get("/api/live-room-analytics/sync/status")
def sync_status(jobId: str = "", _: dict = Depends(security.require_admin)) -> dict:
    if jobId:
        job = store.get_job(jobId)
        return {"ok": bool(job), "job": job}
    running = store.list_jobs(1, 10, "running").get("jobs", [])
    queued = store.list_jobs(1, 10, "queued").get("jobs", [])
    job = (running or queued or [None])[0]
    return {"ok": True, "job": job, "jobs": [item for item in [*(running or []), *(queued or [])] if item]}
