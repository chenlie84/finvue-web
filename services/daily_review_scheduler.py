from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from fastapi import HTTPException

import config
import store
from api import daily_review
from services import tushare_market


logger = logging.getLogger(__name__)
LOCAL_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
STATE_KEY = "daily-review-scheduler-state"
_RUN_LOCK = Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _local_now() -> datetime:
    return datetime.now(LOCAL_TZ)


def _normalize_time(value: Any) -> str:
    text = store.text(value) or "17:40"
    match = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if not match:
        return "17:40"
    hour = max(0, min(23, int(match.group(1))))
    minute = max(0, min(59, int(match.group(2))))
    return f"{hour:02d}:{minute:02d}"


def get_settings() -> dict[str, Any]:
    return {
        "enabled": bool(config.DAILY_MARKET_REVIEW_SCHEDULER_ENABLED),
        "dailyRunTime": _normalize_time(config.DAILY_MARKET_REVIEW_SCHEDULE_TIME),
        "retryMinutes": max(5, int(config.DAILY_MARKET_REVIEW_RETRY_MINUTES or 30)),
        "weekdayOnly": bool(config.DAILY_MARKET_REVIEW_WEEKDAY_ONLY),
    }


def get_state() -> dict[str, Any]:
    saved = store.safe_object(store.get_kv(STATE_KEY, {}))
    return {
        "status": store.text(saved.get("status")) or "idle",
        "localDate": store.text(saved.get("localDate")),
        "tradeDate": store.text(saved.get("tradeDate")),
        "startedAt": store.text(saved.get("startedAt")),
        "finishedAt": store.text(saved.get("finishedAt")),
        "message": store.text(saved.get("message")),
        "error": store.text(saved.get("error")),
        "diagnostics": saved.get("diagnostics") if isinstance(saved.get("diagnostics"), dict) else {},
        "result": saved.get("result") if isinstance(saved.get("result"), dict) else {},
    }


def _set_state(**updates: Any) -> dict[str, Any]:
    state = {**get_state(), **updates, "updatedAt": _now_iso()}
    store.set_kv(STATE_KEY, state)
    return state


def scheduler_status() -> dict[str, Any]:
    settings = get_settings()
    state = get_state()
    token_configured = bool(store.text(tushare_market.get_settings().get("token")))
    return {
        "ok": True,
        "settings": settings,
        "state": state,
        "tokenConfigured": token_configured,
        "enabled": bool(settings.get("enabled") and token_configured),
        "nowLocal": _local_now().isoformat(timespec="seconds"),
    }


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _is_due(settings: dict[str, Any], state: dict[str, Any]) -> tuple[bool, str]:
    if not settings.get("enabled"):
        return False, "scheduler disabled"
    if not store.text(tushare_market.get_settings().get("token")):
        return False, "tushare token missing"
    now = _local_now()
    local_date = now.strftime("%Y-%m-%d")
    if settings.get("weekdayOnly") and now.weekday() >= 5:
        return False, "weekday only"
    hour, minute = [int(part) for part in store.text(settings.get("dailyRunTime")).split(":", 1)]
    scheduled_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < scheduled_at:
        return False, f"waiting for {settings.get('dailyRunTime')}"
    if state.get("localDate") == local_date and state.get("status") == "completed":
        return False, "already completed today"
    if state.get("localDate") == local_date and state.get("status") == "running":
        return False, "already running"
    if state.get("localDate") == local_date and state.get("status") == "failed":
        finished_at = _parse_iso(store.text(state.get("finishedAt") or state.get("updatedAt")))
        if finished_at:
            age_minutes = (datetime.now(timezone.utc) - finished_at).total_seconds() / 60
            if age_minutes < int(settings.get("retryMinutes") or 30):
                return False, "waiting for retry window"
    return True, "due"


def run_once_if_due() -> dict[str, Any]:
    settings = get_settings()
    state = get_state()
    due, reason = _is_due(settings, state)
    if not due:
        return {"ok": True, "ran": False, "reason": reason, "settings": settings, "state": state}
    if not _RUN_LOCK.acquire(blocking=False):
        return {"ok": True, "ran": False, "reason": "lock busy", "settings": settings, "state": state}
    local_date = _local_now().strftime("%Y-%m-%d")
    try:
        _set_state(
            status="running",
            localDate=local_date,
            startedAt=_now_iso(),
            finishedAt="",
            message=f"正在自动生成 {local_date} 行情复盘",
            error="",
            diagnostics={},
            result={},
        )
        result = daily_review._generate_daily_review_payload("", "daily-review-scheduler")
    except HTTPException as exc:
        if isinstance(exc.detail, dict):
            message = store.text(exc.detail.get("message")) or "自动行情复盘生成失败"
            diagnostics = exc.detail.get("diagnostics") if isinstance(exc.detail.get("diagnostics"), dict) else {}
        else:
            message = store.text(exc.detail) or "自动行情复盘生成失败"
            diagnostics = {}
        final_state = _set_state(
            status="failed",
            localDate=local_date,
            finishedAt=_now_iso(),
            message=message,
            error=message,
            diagnostics=diagnostics,
            result={},
        )
        logger.warning("[daily-review-scheduler] generation failed: %s", message)
        return {"ok": False, "ran": True, "error": message, "state": final_state}
    except Exception as exc:
        message = str(exc) or "自动行情复盘生成失败"
        final_state = _set_state(
            status="failed",
            localDate=local_date,
            finishedAt=_now_iso(),
            message=message,
            error=message,
            diagnostics={},
            result={},
        )
        logger.exception("[daily-review-scheduler] generation crashed")
        return {"ok": False, "ran": True, "error": message, "state": final_state}
    finally:
        _RUN_LOCK.release()

    final_state = _set_state(
        status="completed",
        localDate=local_date,
        tradeDate=store.text(result.get("resolvedTradeDate")),
        finishedAt=_now_iso(),
        message=store.text(result.get("message")) or "自动行情复盘已生成",
        error="",
        diagnostics={},
        result={
            "resolvedTradeDate": result.get("resolvedTradeDate"),
            "dateFallback": result.get("dateFallback"),
            "latest": result.get("latest"),
        },
    )
    logger.info("[daily-review-scheduler] generation completed trade_date=%s", result.get("resolvedTradeDate"))
    return {"ok": True, "ran": True, "state": final_state}


async def run_scheduler(stop_event: asyncio.Event) -> None:
    logger.info("[daily-review-scheduler] started")
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(run_once_if_due)
        except Exception:
            logger.exception("[daily-review-scheduler] check failed")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
    logger.info("[daily-review-scheduler] stopped")
