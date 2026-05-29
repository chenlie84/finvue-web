from __future__ import annotations

import asyncio

from services import feishu_push


async def run_scheduler(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        try:
            settings = feishu_push.get_settings()
            if feishu_push.due_to_push(settings):
                await asyncio.to_thread(feishu_push.push_now, settings)
        except Exception as exc:
            print(f"[feishu-scheduler] push failed: {exc}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            pass
