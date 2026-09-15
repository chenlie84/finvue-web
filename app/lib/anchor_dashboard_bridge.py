from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from typing import Any

import pandas as pd
import pymysql


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


# 主播看板外部项目目录：优先读环境变量，未配置时回退到 develop 同级目录
ANCHOR_DASHBOARD_DIR = Path(
    _env("ANCHOR_DASHBOARD_DIR") or str(Path(__file__).resolve().parents[3] / "anchor_dashboard")
)


def fetch_douyin_info_data(sql: str) -> pd.DataFrame:
    host = _env("DOUYIN_DB_HOST")
    if not host:
        raise RuntimeError(
            "缺少抖音数据源配置，请设置 DOUYIN_DB_HOST / DOUYIN_DB_PORT / "
            "DOUYIN_DB_DATABASE / DOUYIN_DB_USER / DOUYIN_DB_PASSWORD 环境变量"
        )
    conn = pymysql.connect(
        host=host,
        port=int(_env("DOUYIN_DB_PORT", "3306")),
        database=_env("DOUYIN_DB_DATABASE", "demo"),
        user=_env("DOUYIN_DB_USER", "root"),
        password=_env("DOUYIN_DB_PASSWORD"),
        charset="utf8",
        connect_timeout=30,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
            columns = [item[0] for item in (cursor.description or [])]
        return pd.DataFrame(list(rows), columns=columns)
    finally:
        conn.close()


def install_base_utils_stub() -> None:
    stub = types.ModuleType("base_utils")
    stub.fetch_douyin_info_data = fetch_douyin_info_data
    sys.modules["base_utils"] = stub


def normalize_payload(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "updated_at": raw.get("updated_at"),
        "summary": raw.get("summary", {}),
        "refresh_stats": raw.get("refresh_stats", {}),
        "weekly_meeting_overview": raw.get("weekly_meeting_overview", {}),
        "anchors": raw.get("anchors", []),
        "anomaly_list": raw.get("anomaly_list", []),
        "replace_pool": raw.get("replace_pool", []),
        "cultivate_pool": raw.get("cultivate_pool", []),
        "resource_summary": raw.get("resource_summary", {}),
        "queues": raw.get("queues", {}),
        "action_records": raw.get("action_records", []),
    }


def main() -> None:
    install_base_utils_stub()
    sys.path.insert(0, str(ANCHOR_DASHBOARD_DIR))
    from app import build_payload  # type: ignore

    start = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "-" else None
    end = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
    payload = build_payload(start, end)
    print(json.dumps(normalize_payload(payload), ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
