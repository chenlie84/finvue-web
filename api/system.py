from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Request, Query

import db
import security
import store


router = APIRouter()


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
    """获取主播画像周会数据，从 finvue_operation_live_stats 表聚合."""
    try:
        now = datetime.now()

        # 解析日期范围
        if start and end:
            try:
                start_date = datetime.strptime(start, "%Y-%m-%d")
                end_date = datetime.strptime(end, "%Y-%m-%d")
            except ValueError:
                start_date = now - timedelta(days=7)
                end_date = now
        else:
            # 默认最近7天
            start_date = now - timedelta(days=7)
            end_date = now

        date_range_start = start_date.strftime("%Y-%m-%d")
        date_range_end = end_date.strftime("%Y-%m-%d")

        # 1. 获取主播汇总数据（按账号聚合）
        anchor_rows = db.fetch_all(
            """
            SELECT
                account,
                COUNT(*) as live_count,
                SUM(duration) as total_duration,
                AVG(duration) as avg_duration,
                AVG(acu) as avg_acu,
                MAX(pcu) as max_pcu,
                SUM(watch_ucnt) as total_watch,
                AVG(watch_ucnt) as avg_watch,
                SUM(follow_ucnt) as total_follow,
                AVG(follow_ucnt) as avg_follow,
                SUM(earn_score) as total_earn,
                MAX(start_time) as last_live_time,
                MIN(start_time) as first_live_time
            FROM finvue_operation_live_stats
            WHERE DATE(start_time) BETWEEN %s AND %s
            GROUP BY account
            ORDER BY total_watch DESC
            """,
            (date_range_start, date_range_end)
        )

        # 2. 获取全局统计
        global_stats = db.fetch_one(
            """
            SELECT
                COUNT(*) as total_live_count,
                COUNT(DISTINCT account) as anchor_count,
                SUM(duration) as total_duration,
                SUM(watch_ucnt) as total_watch,
                SUM(follow_ucnt) as total_follow,
                SUM(earn_score) as total_earn,
                MAX(start_time) as latest_live_time,
                MIN(start_time) as earliest_live_time
            FROM finvue_operation_live_stats
            WHERE DATE(start_time) BETWEEN %s AND %s
            """,
            (date_range_start, date_range_end)
        )

        # 3. 获取最新数据时间
        latest_time_row = db.fetch_one(
            """
            SELECT MAX(start_time) as latest_time FROM finvue_operation_live_stats
            """
        )
        latest_live_time = None
        if latest_time_row and latest_time_row.get("latest_time"):
            latest_live_time = latest_time_row["latest_time"]
            if isinstance(latest_live_time, datetime):
                latest_live_time = latest_live_time.strftime("%Y-%m-%d %H:%M")

        # 构建 anchors 数据（适配前端 anchor-portrait.js 格式）
        anchors = []
        for row in anchor_rows or []:
            account = row.get("account", "")
            live_count = row.get("live_count", 0) or 0
            avg_acu = row.get("avg_acu", 0) or 0
            avg_duration = row.get("avg_duration", 0) or 0
            avg_watch = row.get("avg_watch", 0) or 0
            avg_follow = row.get("avg_follow", 0) or 0
            total_follow = row.get("total_follow", 0) or 0
            total_watch = row.get("total_watch", 0) or 0

            # 计算转粉率（follow_rate = avg_follow / avg_watch，百分比）
            follow_rate = 0.0
            if avg_watch > 0:
                follow_rate = avg_follow / avg_watch

            # 计算停留时长（分钟）
            retention = avg_duration / 60.0 if avg_duration else 0.0

            # 判断状态（基于 ACU 和转粉率）
            status = "yellow"
            if avg_acu >= 500 and follow_rate >= 0.02:
                status = "green"
            elif avg_acu < 100 or follow_rate < 0.005:
                status = "red"

            last_live = row.get("last_live_time")
            if isinstance(last_live, datetime):
                last_live = last_live.strftime("%Y-%m-%d")

            first_live = row.get("first_live_time")
            tenure_months = 0
            if first_live and last_live:
                if isinstance(first_live, datetime):
                    first_live_dt = first_live
                else:
                    try:
                        first_live_dt = datetime.strptime(str(first_live), "%Y-%m-%d")
                    except ValueError:
                        first_live_dt = now
                tenure_months = (now - first_live_dt).days // 30

            anchors.append({
                "account": account,
                "acu": round(avg_acu, 1),
                "retention": round(retention, 2),
                "follow_rate": round(follow_rate, 4),
                "current_fans": int(total_follow),
                "tenure_month": tenure_months,
                "monthly_income": round(row.get("total_earn", 0) or 0 / 10000, 2),  # 万元
                "live_count": live_count,
                "total_watch": total_watch,
                "total_follow": total_follow,
                "avg_duration": round(avg_duration, 0),
                "last_live": last_live or "",
                "week_start": date_range_start,
                "status": status,
                "action": "",
                "quadrant": "",
                "system_action": "待判断",
                "system_status": "未判断",
                "states": {},
                "anomalies": [],
                "pass_ratio": None,
                "manual_override_applied": False
            })

        # 构建 refresh_stats
        refresh_stats = {
            "latest_live_time": latest_live_time,
            "latest_live_date": latest_live_time.split(" ")[0] if latest_live_time else "",
            "total_anchor_count": global_stats.get("anchor_count", 0) or len(anchors),
            "total_live_count": global_stats.get("total_live_count", 0) or 0,
            "date_range_start": date_range_start,
            "date_range_end": date_range_end
        }

        return {
            "ok": True,
            "anchors": anchors,
            "refresh_stats": refresh_stats,
            "summary": {
                "anchor_count": len(anchors),
                "avg_acu": round(sum(a["acu"] for a in anchors) / len(anchors), 1) if anchors else 0,
                "avg_retention": round(sum(a["retention"] for a in anchors) / len(anchors), 2) if anchors else 0,
                "avg_follow_rate": round(sum(a["follow_rate"] for a in anchors) / len(anchors), 4) if anchors else 0,
            },
            "updated_at": now.isoformat(),
            "date_range": {"start": date_range_start, "end": date_range_end}
        }

    except Exception as e:
        import traceback
        print(f"[anchor-dashboard/weekly] Error: {e}")
        traceback.print_exc()
        return {
            "ok": False,
            "anchors": [],
            "refresh_stats": {},
            "error": str(e)
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
