from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

import security
import store


router = APIRouter()


@router.get("/api/jobs")
def list_jobs(page: int = 1, pageSize: int = 20, status: str = "", _: dict = Depends(security.require_permission("live"))) -> dict:
    return store.list_jobs(page, pageSize, status)


@router.post("/api/jobs")
async def create_job(request: Request, _: dict = Depends(security.require_permission("live"))) -> dict:
    body = await request.json()
    job_type = store.text(body.get("type") or body.get("jobType"))
    if not job_type:
        raise HTTPException(status_code=400, detail="缺少任务类型")
    return store.enqueue_job(job_type, body.get("payload") or body)


@router.post("/api/jobs/retry")
async def retry_job(request: Request, _: dict = Depends(security.require_permission("live"))) -> dict:
    body = await request.json()
    job_id = store.text(body.get("id") or body.get("jobId"))
    job = store.retry_job(job_id) if job_id else None
    if not job:
        raise HTTPException(status_code=404, detail="未找到任务")
    return job
