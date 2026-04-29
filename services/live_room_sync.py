from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

import config
import store


BRIDGE_PATH = config.BASE_DIR / "app" / "lib" / "live_room_analytics_sync_bridge.py"


def _python_executable() -> str:
    configured = str(config.ANCHOR_DASHBOARD_PYTHON or "").strip()
    if configured:
        return configured
    return sys.executable


def _latest_sync_cursor() -> str:
    row = store.db.fetch_one("SELECT MAX(analyzed_at) AS latest_at FROM customer_sessions WHERE report_type = 'dbLiveAnalytics'")
    return store.iso(row.get("latest_at")) if row and row.get("latest_at") else ""


def fetch_bridge_payload(*, since: str = "", force_full: bool = False) -> dict[str, Any]:
    if not BRIDGE_PATH.exists():
        raise RuntimeError(f"抖音同步桥接脚本不存在：{BRIDGE_PATH}")
    python_bin = _python_executable()
    args = [python_bin, str(BRIDGE_PATH)]
    if since and not force_full:
        args.extend(["--since", since])
    env = os.environ.copy()
    lib_dir = str(BRIDGE_PATH.parent)
    env["PYTHONPATH"] = lib_dir + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    try:
        proc = subprocess.run(
            args,
            cwd=lib_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=int(os.environ.get("DOUYIN_SYNC_TIMEOUT_SECONDS", "900")),
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"抖音同步 Python 不存在或不可执行：{python_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("抖音同步超时，请缩小时间范围或检查数据源响应") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"抖音同步桥接脚本执行失败：{detail[:2000] or proc.returncode}")
    try:
        payload = json.loads(proc.stdout or "{}")
    except Exception as exc:
        raise RuntimeError(f"抖音同步返回内容不是合法 JSON：{str(proc.stdout or '')[:1000]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("抖音同步返回结构异常：根节点不是对象")
    return payload


def run_sync(payload: dict[str, Any], progress: Callable[[int, str, str, dict[str, Any] | None], None] | None = None) -> dict[str, Any]:
    progress = progress or (lambda *_args, **_kwargs: None)
    force_full = bool(payload.get("forceFull") or payload.get("full"))
    since = str(payload.get("since") or "").strip()
    if not since and not force_full:
        since = _latest_sync_cursor()
    mode = "full" if force_full or not since else "incremental"

    progress(8, "prepare", "准备读取抖音直播数据库", {"mode": mode, "since": since})
    data = fetch_bridge_payload(since=since, force_full=force_full)
    meta = store.safe_object(data.get("meta"))
    progress(55, "query", "抖音数据读取完成，正在合并主播与客户资料", meta)

    anchors = store.safe_array(data.get("anchors"))
    customers = store.safe_array(data.get("customers"))
    anchor_count = store.upsert_anchor_profiles(anchors)
    customer_result = store.upsert_customer_entries(customers)
    result_meta = {
        **meta,
        "mode": mode,
        "saved_anchor_count": anchor_count,
        "saved_customer_count": customer_result.get("customers", 0),
        "saved_customer_session_count": customer_result.get("sessions", 0),
    }
    progress(92, "save", "数据已写入 MySQL，正在刷新聚合结果", result_meta)
    return {
        "ok": True,
        "message": "数据库同步完成",
        "phase": "done",
        "meta": result_meta,
    }

