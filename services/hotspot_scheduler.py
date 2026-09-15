"""Background scheduler for hotspot refresh."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import config
import db
from services import scheduler_guard
from services.hotspot_fetcher import cleanup_old_data, has_expired_data, sync_fetch_all_platforms


logger = logging.getLogger(__name__)


def _parse_json(value: Any, fallback: Any = None) -> Any:
    import json

    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def _settings() -> dict[str, Any]:
    row = db.fetch_one(
        "SELECT enabled_platforms, fetch_interval_minutes, retention_days"
        " FROM finvue_hotspot_settings WHERE id = 'default'"
    )
    if not row:
        return {"platforms": None, "interval_minutes": 60, "retention_days": 30}
    platforms = _parse_json(row.get("enabled_platforms"), [])
    interval = int(row.get("fetch_interval_minutes") or 60)
    retention = int(row.get("retention_days") or 30)
    return {
        "platforms": platforms or None,
        "interval_minutes": max(15, interval),
        "retention_days": max(1, retention),
    }


def _latest_seen_at() -> datetime | None:
    row = db.fetch_one("SELECT MAX(last_seen_at) AS latest_at FROM finvue_hotspot_items")
    value = row.get("latest_at") if row else None
    return value if isinstance(value, datetime) else None


def _refresh_if_due() -> None:
    settings = _settings()
    interval_minutes = settings["interval_minutes"]
    latest_at = _latest_seen_at()
    if latest_at and datetime.now() - latest_at < timedelta(minutes=interval_minutes):
        return

    platforms = settings["platforms"]
    logger.info("[hotspot_scheduler] refresh due interval=%s platforms=%s", interval_minutes, platforms)
    result = scheduler_guard.run_guarded(
        "hotspot-refresh",
        sync_fetch_all_platforms,
        source="hotspot-scheduler",
        platforms=platforms,
    )
    logger.info("[hotspot_scheduler] refresh result=%s", result)


def _cleanup_if_due() -> None:
    """过期数据清理。

    这里才是真正跑着的那条路径——cleanup_old_data 之前只挂在管理端接口、
    worker 任务类型和 hotspot_cron.py 上，而线上抓取由本调度器驱动，
    没人调清理，快照表于是只增不减（19 天堆到 29813 条）。
    用「有没有过期快照」作为触发条件，天然幂等，不用额外记录上次清理时间。
    """
    retention_days = _settings()["retention_days"]
    if not has_expired_data(retention_days):
        return

    logger.info("[hotspot_scheduler] cleanup due retention_days=%s", retention_days)
    result = scheduler_guard.run_guarded(
        "hotspot-cleanup",
        cleanup_old_data,
        source="hotspot-scheduler",
        ttl_seconds=30 * 60,
        retention_days=retention_days,
    )
    logger.info("[hotspot_scheduler] cleanup result=%s", result)


async def run_scheduler(stop_event: asyncio.Event) -> None:
    """Run until stop_event is set."""
    logger.info("[hotspot_scheduler] started")
    while not stop_event.is_set():
        try:
            if config.HOTSPOT_API_ENABLED and config.has_mysql_config():
                await asyncio.to_thread(_refresh_if_due)
                await asyncio.to_thread(_cleanup_if_due)
        except Exception:
            logger.exception("[hotspot_scheduler] refresh failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
    logger.info("[hotspot_scheduler] stopped")
