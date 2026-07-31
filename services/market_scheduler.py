from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import store
from services import scheduler_guard
from services import tushare_market


def _age_minutes(value: str) -> float:
    if not value:
        return 10**9
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() / 60
    except Exception:
        return 10**9


async def run_scheduler(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            settings = tushare_market.get_settings()
            if settings.get("enabled") and settings.get("token"):
                cache = store.safe_object(tushare_market.get_cached_snapshot())
                if _age_minutes(str(cache.get("updatedAt") or "")) >= int(settings.get("intervalMinutes") or 60):
                    await asyncio.to_thread(
                        scheduler_guard.run_guarded,
                        "market-refresh",
                        tushare_market.fetch_market_snapshot,
                        source="tushare-market-scheduler",
                        settings=settings,
                    )
        except Exception as exc:
            print(f"[market-scheduler] fetch failed: {exc}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
