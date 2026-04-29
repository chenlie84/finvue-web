from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pandas as pd
import pymysql


ANCHOR_DASHBOARD_DIR = Path("/Users/beeerjack/Desktop/develop/anchor_dashboard")


def fetch_douyin_info_data(sql: str) -> pd.DataFrame:
    conn = pymysql.connect(
        host="10.170.32.218",
        port=3306,
        database="demo",
        user="root",
        password="Python3.8",
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
