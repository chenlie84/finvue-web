from __future__ import annotations

import time
from datetime import datetime
from typing import Any


RUN_STARTED_AT = time.monotonic()


def build_progress_event(stage: str, **fields: Any) -> dict[str, Any]:
    trade_date = fields.pop("trade_date", "") or fields.pop("requested_date", "")
    payload = {
        "event": "daily_market_review_progress",
        "stage": stage,
        "trade_date": trade_date,
        "elapsed_seconds": round(time.monotonic() - RUN_STARTED_AT, 3),
        "source": fields.pop("source", ""),
        "fallback_reason": fields.pop("fallback_reason", ""),
        "error_code": fields.pop("error_code", ""),
        "ts": datetime.now().isoformat(timespec="seconds"),
    }
    payload.update(fields)
    return payload
