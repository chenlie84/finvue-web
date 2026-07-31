"""Background scheduler for hotspot refresh."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

import config
import db
from services import scheduler_guard
from services.hotspot_fetcher import sync_fetch_all_platforms


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
    row = db.fetch_one("SELECT enabled_platforms, fetch_interval_minutes FROM finvue_hotspot_settings WHERE id = 'default'")
    if not row:
        return {"platforms": None, "interval_minutes": 60}
    platforms = _parse_json(row.get("enabled_platforms"), [])
    interval = int(row.get("fetch_interval_minutes") or 60)
    return {"platforms": platforms or None, "interval_minutes": max(15, interval)}


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


async def run_scheduler(stop_event: asyncio.Event) -> None:
    """Run until stop_event is set."""
    logger.info("[hotspot_scheduler] started")
    while not stop_event.is_set():
        try:
            if config.HOTSPOT_API_ENABLED and config.has_mysql_config():
                await asyncio.to_thread(_refresh_if_due)
        except Exception:
            logger.exception("[hotspot_scheduler] refresh failed")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
    logger.info("[hotspot_scheduler] stopped")
