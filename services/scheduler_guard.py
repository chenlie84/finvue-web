"""Shared database-backed scheduler locks and observable task status."""
from __future__ import annotations

import logging
import os
import socket
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import db
import store


logger = logging.getLogger(__name__)
DEFAULT_TASKS = ("hotspot-refresh", "market-refresh", "feishu-push", "daily-review")
DEFAULT_TTL_SECONDS = 15 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat().replace("+00:00", "Z")


def _owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


def _state_key(task_name: str) -> str:
    return f"scheduler:{task_name}:state"


def acquire_lock(task_name: str, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Return lock owner token when acquired, otherwise an empty string."""
    owner = _owner()
    locked_until = (_now() + timedelta(seconds=max(30, ttl_seconds))).strftime("%Y-%m-%d %H:%M:%S")
    now_sql = _now().strftime("%Y-%m-%d %H:%M:%S")
    key = f"scheduler:{task_name}"
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO finvue_scheduler_locks (`key`, owner, locked_until)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    owner = IF(locked_until <= %s, VALUES(owner), owner),
                    locked_until = IF(locked_until <= %s, VALUES(locked_until), locked_until),
                    updated_at = IF(locked_until <= %s, CURRENT_TIMESTAMP, updated_at)
                """,
                (key, owner, locked_until, now_sql, now_sql, now_sql),
            )
            cur.execute("SELECT owner FROM finvue_scheduler_locks WHERE `key` = %s", (key,))
            row = cur.fetchone()
        if row and row.get("owner") == owner:
            return owner
    except Exception:
        logger.exception("[scheduler-guard] acquire lock failed task=%s", task_name)
    return ""


def release_lock(task_name: str, owner: str) -> None:
    if not owner:
        return
    try:
        db.execute("DELETE FROM finvue_scheduler_locks WHERE `key` = %s AND owner = %s", (f"scheduler:{task_name}", owner))
    except Exception:
        logger.exception("[scheduler-guard] release lock failed task=%s", task_name)


def record_status(task_name: str, **updates: Any) -> dict[str, Any]:
    current = store.safe_object(store.get_kv(_state_key(task_name), {}))
    state = {**current, **updates, "taskName": task_name, "updatedAt": _now_iso()}
    store.set_kv(_state_key(task_name), state)
    return state


def run_guarded(task_name: str, fn, *, ttl_seconds: int = DEFAULT_TTL_SECONDS, source: str = "", **kwargs: Any) -> dict[str, Any]:
    owner = acquire_lock(task_name, ttl_seconds=ttl_seconds)
    if not owner:
        return record_status(task_name, status="skipped", skippedReason="lock busy", source=source)
    started = time.monotonic()
    started_at = _now_iso()
    record_status(task_name, status="running", startedAt=started_at, lastError="", source=source)
    try:
        result = fn(*kwargs.pop("_args", ()), **kwargs)
    except Exception as exc:
        elapsed = round(time.monotonic() - started, 3)
        state = record_status(
            task_name,
            status="failed",
            startedAt=started_at,
            finishedAt=_now_iso(),
            elapsedSeconds=elapsed,
            lastError=str(exc) or exc.__class__.__name__,
            source=source,
        )
        raise
    else:
        elapsed = round(time.monotonic() - started, 3)
        return record_status(
            task_name,
            status="completed",
            startedAt=started_at,
            finishedAt=_now_iso(),
            elapsedSeconds=elapsed,
            lastError="",
            source=source,
            result=result if isinstance(result, dict) else {},
        )
    finally:
        release_lock(task_name, owner)


def list_status(task_names: tuple[str, ...] = DEFAULT_TASKS) -> dict[str, Any]:
    items: dict[str, Any] = {}
    for task_name in task_names:
        items[task_name] = store.safe_object(store.get_kv(_state_key(task_name), {})) or {
            "taskName": task_name,
            "status": "idle",
            "updatedAt": "",
        }
    return items
