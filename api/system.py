from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Query

import config
import security
import store


router = APIRouter()

ANCHOR_DASHBOARD_BRIDGE = Path(__file__).parent.parent / "app" / "lib" / "anchor_dashboard_bridge.py"


@router.get("/api/health")
def health() -> dict:
    return {"ok": True, "runtime": "fastapi", "database": "mysql"}


@router.get("/api/anchor-dashboard/weekly")
def dashboard_weekly(
    force: bool = Query(False),
    start: str = Query(""),
    end: str = Query(""),
    _: dict = Depends(security.require_permission("home"))
) -> dict:
    """获取主播画像周会数据，通过 anchor_dashboard_bridge 调用外部 anchor_dashboard 模块."""
    python_path = str(config.ANCHOR_DASHBOARD_PYTHON or "python3").strip()
    if not ANCHOR_DASHBOARD_BRIDGE.exists():
        return {
            "ok": False,
            "anchors": [],
            "refresh_stats": {},
            "error": "anchor_dashboard_bridge.py 脚本不存在",
            "message": "请确保 app/lib/anchor_dashboard_bridge.py 文件存在"
        }

    try:
        args = [python_path, str(ANCHOR_DASHBOARD_BRIDGE)]
        if start:
            args.append(start)
        else:
            args.append("-")
        if end:
            args.append(end)
        else:
            args.append("-")

        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(ANCHOR_DASHBOARD_BRIDGE.parent.parent.parent)
        )

        if result.returncode != 0:
            error_msg = result.stderr.strip() or result.stdout.strip() or "未知错误"
            return {
                "ok": False,
                "anchors": [],
                "refresh_stats": {},
                "error": f"anchor_dashboard_bridge 执行失败: {error_msg}",
                "returncode": result.returncode
            }

        payload = json.loads(result.stdout)
        payload["ok"] = True
        return payload

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "anchors": [],
            "refresh_stats": {},
            "error": "anchor_dashboard_bridge 执行超时（60秒）"
        }
    except json.JSONDecodeError as e:
        return {
            "ok": False,
            "anchors": [],
            "refresh_stats": {},
            "error": f"JSON 解析失败: {e.msg}",
            "raw_output": result.stdout[:500] if result else ""
        }
    except Exception as e:
        return {
            "ok": False,
            "anchors": [],
            "refresh_stats": {},
            "error": f"执行异常: {str(e)}"
        }


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
