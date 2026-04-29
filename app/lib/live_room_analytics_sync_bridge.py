from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from anchor_dashboard_bridge import fetch_douyin_info_data

MAX_RANKS_PER_METRIC = 0
RANK_FIELD_FILTER = """
      and (
        rank_watch is not null and rank_watch <> ''
        or rank_like is not null and rank_like <> ''
        or rank_first is not null and rank_first <> ''
      )
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="", help="Only sync rows created at or after this datetime")
    return parser.parse_args()


CHUNK_DAYS = 31


def normalize_since_for_sql(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except Exception:
            return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def normalize_sql_datetime(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw, fmt)
                break
            except Exception:
                dt = None
        if dt is None:
            return ""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse_sql_datetime(value: Any) -> datetime | None:
    normalized = normalize_sql_datetime(value)
    if not normalized:
        return None
    try:
        return datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def build_created_at_clause(start: str = "", end: str = "") -> str:
    parts: list[str] = []
    if start:
        parts.append(f" created_at >= '{start}'")
    if end:
        parts.append(f" created_at < '{end}'")
    if not parts:
        return ""
    return " and " + " and ".join(parts)


def build_customer_sql(created_at_clause: str = "") -> str:
    return r"""
    select account, room_id, created_at, rank_watch, rank_like, rank_first, overview, fans_group_pie
    from douyin_creator_live_room_analytics_data
    where account is not null
      and room_id is not null
    """ + created_at_clause + RANK_FIELD_FILTER


def build_anchor_sql(created_at_clause: str = "") -> str:
    return """
    select t.account, t.room_id, t.fans_group_pie, t.overview, t.created_at
    from douyin_creator_live_room_analytics_data t
    inner join (
      select account, max(created_at) as latest_created_at
      from douyin_creator_live_room_analytics_data
      where account is not null
    """ + created_at_clause + """
      group by account
    ) latest
      on latest.account = t.account
     and latest.latest_created_at = t.created_at
    where t.account is not null
    """ + created_at_clause


def fetch_customer_rows_incremental(since_sql: str) -> list[dict[str, Any]]:
    customer_df = fetch_douyin_info_data(build_customer_sql(build_created_at_clause(start=since_sql)))
    if customer_df is None or customer_df.empty:
        return []
    return customer_df.to_dict(orient="records")


def fetch_customer_rows_full() -> list[dict[str, Any]]:
    bounds_sql = """
    select min(created_at) as min_created_at, max(created_at) as max_created_at
    from douyin_creator_live_room_analytics_data
    where account is not null
      and room_id is not null
    """ + RANK_FIELD_FILTER
    bounds_df = fetch_douyin_info_data(bounds_sql)
    if bounds_df is None or bounds_df.empty:
        return []
    bounds = bounds_df.to_dict(orient="records")[0]
    start_dt = parse_sql_datetime(bounds.get("min_created_at"))
    end_dt = parse_sql_datetime(bounds.get("max_created_at"))
    if not start_dt or not end_dt:
        return []

    rows: list[dict[str, Any]] = []
    cursor = start_dt
    while cursor <= end_dt:
        next_cursor = min(cursor + timedelta(days=CHUNK_DAYS), end_dt + timedelta(seconds=1))
        clause = build_created_at_clause(
            start=cursor.strftime("%Y-%m-%d %H:%M:%S"),
            end=next_cursor.strftime("%Y-%m-%d %H:%M:%S"),
        )
        chunk_df = fetch_douyin_info_data(build_customer_sql(clause))
        if chunk_df is not None and not chunk_df.empty:
            rows.extend(chunk_df.to_dict(orient="records"))
        cursor = next_cursor
    return rows


def parse_nested_json(value: Any) -> dict[str, Any]:
    current = value
    for _ in range(4):
        if current is None:
            return {}
        if isinstance(current, str):
            current = current.strip()
            if not current:
                return {}
            try:
                current = json.loads(current)
                continue
            except Exception:
                return {}
        if isinstance(current, dict):
            if "data" in current and isinstance(current["data"], str):
                try:
                    current = json.loads(current["data"])
                    continue
                except Exception:
                    pass
            if "data" in current and isinstance(current["data"], dict):
                current = current["data"]
                continue
            return current
        return {}
    return current if isinstance(current, dict) else {}


def parse_json_list(value: Any) -> list[Any]:
    current = value
    for _ in range(3):
        if current is None:
            return []
        if isinstance(current, str):
            current = current.strip()
            if not current:
                return []
            try:
                current = json.loads(current)
                continue
            except Exception:
                return []
        if isinstance(current, list):
            return current
        return []
    return current if isinstance(current, list) else []


def parse_timestamp(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return datetime.now(timezone.utc).isoformat()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19], fmt).replace(tzinfo=timezone.utc).isoformat()
        except Exception:
            pass
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        ts = int(float(raw))
        if ts > 10_000_000_000:
            ts = ts / 1000
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def parse_number(value: Any, default: float = 0.0) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return default
    num = []
    seen_dot = False
    seen_sign = False
    for ch in text:
        if ch.isdigit():
            num.append(ch)
        elif ch == "." and not seen_dot:
            seen_dot = True
            num.append(ch)
        elif ch == "-" and not seen_sign and not num:
            seen_sign = True
            num.append(ch)
    if not num or "".join(num) in {"-", ".", "-."}:
        return default
    try:
        return float("".join(num))
    except Exception:
        return default


def parse_watch_seconds(value: Any) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    if "小时" in text or "分" in text or "秒" in text:
        hours = parse_number(text.split("小时")[0]) if "小时" in text else 0
        minutes = 0
        seconds = 0
        if "分" in text:
            part = text.split("小时")[-1] if "小时" in text else text
            minutes = parse_number(part.split("分")[0])
        if "秒" in text:
            part = text.split("分")[-1] if "分" in text else text
            seconds = parse_number(part.split("秒")[0])
        return int(hours * 3600 + minutes * 60 + seconds)
    value_num = parse_number(text, 0)
    if value_num <= 0:
        return 0
    return int(value_num * 60)


def unique_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    return items


def extract_overview_metrics(overview_payload: dict[str, Any]) -> dict[str, Any]:
    series = overview_payload.get("series") or []
    item = series[0] if series else {}
    return {
        "acu": parse_number(item.get("acu")),
        "avgWatchDuration": parse_number(item.get("avgWatchDuration") or item.get("avg_watch_duration")),
        "commentRate": parse_number(item.get("commentRate") or item.get("comment_rate")),
        "consumeRate": parse_number(item.get("consumeRate") or item.get("consume_rate")),
        "duration": str(item.get("duration") or item.get("live_duration") or "").strip(),
        "earnScore": parse_number(item.get("earnScore") or item.get("earn_score")),
        "commentUcnt": parse_number(item.get("commentUcnt") or item.get("comment_ucnt")),
        "consumeUcnt": parse_number(item.get("consumeUcnt") or item.get("consume_ucnt")),
    }


def extract_overview_item(overview_payload: dict[str, Any]) -> dict[str, Any]:
    series = overview_payload.get("series") or []
    return series[0] if series and isinstance(series[0], dict) else {}


def extract_live_started_at(row: dict[str, Any], overview_item: dict[str, Any] | None = None) -> str:
    item = overview_item if isinstance(overview_item, dict) else extract_overview_item(parse_nested_json(row.get("overview")))
    started_at = (
        item.get("startTime")
        or item.get("start_time")
        or item.get("startTs")
        or item.get("start_ts")
        or row.get("created_at")
    )
    return parse_timestamp(started_at)


def extract_fans_segments(payload: dict[str, Any]) -> list[str]:
    series = payload.get("series") or []
    labels = []
    for item in series:
        name = str(item.get("name") or "").strip()
        ratio = str(item.get("ratio") or "").strip()
        value = str(item.get("value") or "").strip()
        if not name:
            continue
        suffix = []
        if ratio:
            suffix.append(f"{ratio}%")
        if value:
            suffix.append(f"{value}人")
        labels.append(f"{name} {' '.join(suffix)}".strip())
    return labels


def extract_rank_items(value: Any) -> list[dict[str, Any]]:
    payload = parse_nested_json(value)
    ranks = payload.get("ranks") if isinstance(payload, dict) else None
    if not isinstance(ranks, list):
        return []
    return [item for item in ranks if isinstance(item, dict)]


def build_live_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    overview = parse_nested_json(row.get("overview"))
    fans_group = parse_nested_json(row.get("fans_group_pie"))
    metrics = extract_overview_metrics(overview)
    fan_segments = extract_fans_segments(fans_group)
    item = extract_overview_item(overview)
    title = str(item.get("title") or "").strip()
    started_at = extract_live_started_at(row, item)
    return {
        "roomId": str(row.get("room_id") or "").strip(),
        "liveTitle": title,
        "startTime": started_at,
        "duration": str(metrics.get("duration") or "").strip(),
        "acu": int(parse_number(metrics.get("acu"), 0)),
        "avgWatchDuration": float(parse_number(metrics.get("avgWatchDuration"), 0)),
        "commentRate": float(parse_number(metrics.get("commentRate"), 0)),
        "consumeRate": float(parse_number(metrics.get("consumeRate"), 0)),
        "earnScore": float(parse_number(metrics.get("earnScore"), 0)),
        "commentUcnt": int(parse_number(metrics.get("commentUcnt"), 0)),
        "consumeUcnt": int(parse_number(metrics.get("consumeUcnt"), 0)),
        "fanSegments": fan_segments,
    }


def build_customer_session(account: str, room_id: str, created_at: Any, rank_item: dict[str, Any], metric_type: str, live_snapshot: dict[str, Any]) -> dict[str, Any]:
    user = rank_item.get("user") or {}
    nickname = str(user.get("nickname") or "").strip() or "未命名客户"
    customer_id = str(user.get("id_str") or user.get("id") or "").strip()
    metric_value = str(rank_item.get("value") or "").strip()
    pay_grade = user.get("pay_grade") or {}
    fans_club = user.get("fans_club") or {}
    tags = [metric_type]
    if user.get("is_follower"):
        tags.append("粉丝")
    level = pay_grade.get("level")
    if level:
        tags.append(f"消费等级{level}")
    club_data = fans_club.get("data") or {}
    if club_data.get("badge"):
        tags.append("粉丝团")
    session_id = f"db::{room_id}::{metric_type}::{customer_id or nickname}"
    analyzed_at = str(live_snapshot.get("startTime") or "") or parse_timestamp(created_at)
    watch_seconds = int(parse_number(rank_item.get("watch_time"), 0))
    watch_raw = ""
    if metric_type == "观看榜":
        watch_raw = metric_value or (f"{watch_seconds}秒" if watch_seconds else "")
    return {
        "customerId": customer_id,
        "customerName": nickname,
        "session": {
            "sessionId": session_id,
            "customerId": customer_id,
            "analyzedAt": analyzed_at,
            "anchorName": account,
            "roomId": room_id,
            "liveTheme": str(live_snapshot.get("liveTitle") or ""),
            "reportType": "dbLiveAnalytics",
            "metricType": metric_type,
            "metricValue": metric_value,
            "analysisSummary": f"{metric_type}第 {int(parse_number(rank_item.get('rank'), 0) or 0)} 名，指标值 {metric_value or '0'}",
            "complianceLevel": "",
            "sourceFile": "douyin_creator_live_room_analytics_data",
            "watchRank": int(parse_number(rank_item.get("rank"), 0)),
            "watchDurationRaw": watch_raw,
            "watchDurationSeconds": watch_seconds if watch_seconds > 0 else parse_watch_seconds(watch_raw),
            "contributionValue": str(rank_item.get("contribute_value") or metric_value) if metric_type in {"点赞榜", "首关榜"} else "",
            "firstGift": str(rank_item.get("first_gift") or ""),
            "commentCount": "",
            "likeCount": metric_value if metric_type == "点赞榜" else "",
            "accompanyCount": "",
            "customerAge": int(parse_number(user.get("age"), 0)),
            "customerGender": int(parse_number(user.get("gender"), 0)),
            "customerLocation": str(user.get("location") or "").strip(),
            "isFollower": bool(user.get("is_follower")),
            "payLevel": int(parse_number(pay_grade.get("level"), 0)),
            "fansClubLevel": int(parse_number(club_data.get("level"), 0)),
            "labels": tags,
            "tags": tags,
            "liveMetrics": live_snapshot,
        },
    }


def build_anchor_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    account = str(row.get("account") or "").strip() or "未命名主播"
    room_id = str(row.get("room_id") or "").strip()
    overview = parse_nested_json(row.get("overview"))
    fans_group = parse_nested_json(row.get("fans_group_pie"))
    overview_item = extract_overview_item(overview)
    analyzed_at = extract_live_started_at(row, overview_item)
    overview_metrics = extract_overview_metrics(overview)
    fan_segments = extract_fans_segments(fans_group)
    summary_parts = [
        f"数据库回填场次 {room_id}" if room_id else "数据库回填场次",
        f"在线峰值 {int(overview_metrics['acu'])}" if overview_metrics["acu"] else "",
        f"平均观看 {overview_metrics['avgWatchDuration']}" if overview_metrics["avgWatchDuration"] else "",
        f"评论率 {overview_metrics['commentRate']}" if overview_metrics["commentRate"] else "",
        f"转化率 {overview_metrics['consumeRate']}" if overview_metrics["consumeRate"] else "",
    ]
    summary = "，".join([item for item in summary_parts if item]) or "直播数据库同步快照"
    return {
        "anchorName": account,
        "snapshot": {
            "id": f"{account}-{room_id or analyzed_at}".replace(" ", "-"),
            "analyzedAt": analyzed_at,
            "reportType": "dbLiveAnalytics",
            "institutionScene": "抖音直播数据库同步",
            "liveTheme": "",
            "complianceLevel": "",
            "contentSchool": "",
            "personaEmpathy": "",
            "commercialLogic": "",
            "coreSummary": summary,
            "classifications": fan_segments,
            "tags": fan_segments,
            "scores": {},
            "evidence": {
                "summary": [summary],
                "compliance": [],
            },
            "markdown": "",
        },
        "profile": {
            "anchorName": account,
            "latestAnalyzedAt": analyzed_at,
            "updatedAt": datetime.now(timezone.utc).isoformat(),
            "institutionScene": "抖音直播数据库同步",
            "latestReportType": "dbLiveAnalytics",
            "liveTheme": "",
            "complianceLevel": "",
            "contentSchool": "",
            "personaEmpathy": "",
            "commercialLogic": "",
            "coreSummary": summary,
            "classifications": fan_segments,
            "tags": fan_segments,
            "scores": {},
            "evidence": {
                "summary": [summary],
                "compliance": [],
            },
        },
    }


def main() -> None:
    args = parse_args()
    since_sql = normalize_since_for_sql(args.since)
    customer_records = fetch_customer_rows_incremental(since_sql) if since_sql else fetch_customer_rows_full()
    anchor_df = fetch_douyin_info_data(build_anchor_sql(build_created_at_clause(start=since_sql)))

    if not customer_records and (anchor_df is None or anchor_df.empty):
        print(json.dumps({"anchors": [], "customers": [], "meta": {"rows": 0}}, ensure_ascii=False))
        return

    customer_rows: list[dict[str, Any]] = []
    for row in customer_records:
        account = str(row.get("account") or "").strip()
        if not account:
            continue
        live_snapshot = build_live_snapshot(row)
        for field_name, metric_type in (
            ("rank_watch", "观看榜"),
            ("rank_like", "点赞榜"),
            ("rank_first", "首关榜"),
        ):
            ranks = extract_rank_items(row.get(field_name))
            selected_ranks = ranks[:MAX_RANKS_PER_METRIC] if MAX_RANKS_PER_METRIC > 0 else ranks
            for rank_item in selected_ranks:
                if not isinstance(rank_item, dict):
                    continue
                customer_rows.append(
                    build_customer_session(
                        account=account,
                        room_id=str(row.get("room_id") or "").strip(),
                        created_at=row.get("created_at"),
                        rank_item=rank_item,
                        metric_type=metric_type,
                        live_snapshot=live_snapshot,
                    )
                )

    customer_groups: dict[str, dict[str, Any]] = {}
    now_iso = datetime.now(timezone.utc).isoformat()
    for item in customer_rows:
        customer_id = str(item.get("customerId") or "").strip()
        customer_name = str(item.get("customerName") or "").strip() or "未命名客户"
        session = item.get("session") or {}
        key = customer_id or customer_name.lower()
        current = customer_groups.get(key)
        if current is None:
            customer_groups[key] = {
                "id": f"customer-{key}",
                "customerId": customer_id,
                "customerName": customer_name,
                "updatedAt": now_iso,
                "latestAnalyzedAt": str(session.get("analyzedAt") or ""),
                "latestAnchorName": str(session.get("anchorName") or ""),
                "latestLiveTheme": str(session.get("liveTheme") or ""),
                "latestWatchDuration": str(session.get("watchDurationRaw") or ""),
                "latestRank": int(parse_number(session.get("watchRank"), 0)),
                "labels": list(session.get("labels") or []),
                "tags": list(session.get("tags") or []),
                "sessions": [session],
            }
            continue
        current["sessions"].append(session)
        current["labels"] = unique_strings(list(current.get("labels") or []) + list(session.get("labels") or []))
        current["tags"] = unique_strings(list(current.get("tags") or []) + list(session.get("tags") or []))
        latest_at = str(current.get("latestAnalyzedAt") or "")
        next_at = str(session.get("analyzedAt") or "")
        if next_at and next_at >= latest_at:
            current["latestAnalyzedAt"] = next_at
            current["latestAnchorName"] = str(session.get("anchorName") or "")
            current["latestLiveTheme"] = str(session.get("liveTheme") or "")
            current["latestWatchDuration"] = str(session.get("watchDurationRaw") or "")
            current["latestRank"] = int(parse_number(session.get("watchRank"), 0))

    anchors = []
    for row in (anchor_df.to_dict(orient="records") if anchor_df is not None and not anchor_df.empty else []):
        latest = build_anchor_snapshot(row)
        anchors.append({
            "id": latest["profile"]["anchorName"],
            **latest["profile"],
            "snapshots": [latest["snapshot"]],
        })

    print(json.dumps({
        "anchors": anchors,
        "customers": list(customer_groups.values()),
        "meta": {
            "rows": int(len(customer_records) + (len(anchor_df) if anchor_df is not None else 0)),
            "anchor_count": len(anchors),
            "customer_session_count": len(customer_rows),
            "customer_count": len(customer_groups),
            "since": since_sql,
            "chunk_days": CHUNK_DAYS if not since_sql else 0,
        },
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
