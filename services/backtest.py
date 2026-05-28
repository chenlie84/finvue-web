from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Any

import db
import store
from services import tushare_market


POSITIVE_WORDS = ["看多", "机会", "配置", "超配", "利好", "上行", "反弹", "突破", "修复", "增配", "走强", "关注"]
NEGATIVE_WORDS = ["看空", "规避", "风险", "回避", "减配", "利空", "承压", "调整", "下跌", "走弱", "谨慎"]

THEME_TARGETS = [
    {"name": "大盘方向", "code": "000300.SH", "api": "index_daily", "keywords": ["大盘", "指数", "沪深300", "市场", "A股"]},
    {"name": "创业板成长", "code": "399006.SZ", "api": "index_daily", "keywords": ["创业板", "成长", "科技成长"]},
    {"name": "中证500中盘", "code": "000905.SH", "api": "index_daily", "keywords": ["中证500", "中盘", "中小盘"]},
    {"name": "半导体", "code": "600584.SH", "api": "daily", "keywords": ["半导体", "芯片", "存储", "AI算力", "算力", "PCB", "电子"]},
    {"name": "新能源车", "code": "300750.SZ", "api": "daily", "keywords": ["新能源", "锂电", "电池", "汽车", "光伏"]},
    {"name": "医药生物", "code": "603259.SH", "api": "daily", "keywords": ["医药", "创新药", "医疗", "生物"]},
    {"name": "金融地产", "code": "600036.SH", "api": "daily", "keywords": ["银行", "券商", "保险", "地产", "红利"]},
    {"name": "白酒消费", "code": "600519.SH", "api": "daily", "keywords": ["消费", "白酒", "食品", "零售"]},
]


def _iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw[:10]


def _api_date(value: str) -> str:
    return re.sub(r"\D", "", value or "")[:8]


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")


def list_anchors() -> dict[str, Any]:
    rows = db.fetch_all(
        """
        SELECT anchor_name AS anchorName, COUNT(*) AS reportCount, MAX(created_at) AS latestAt
        FROM finvue_analysis_reports
        WHERE anchor_name IS NOT NULL AND anchor_name <> ''
        GROUP BY anchor_name
        ORDER BY latestAt DESC
        LIMIT 200
        """
    )
    profile_rows = db.fetch_all(
        """
        SELECT anchor_name AS anchorName, updated_at AS latestAt
        FROM finvue_anchor_profiles
        WHERE anchor_name IS NOT NULL AND anchor_name <> ''
        ORDER BY updated_at DESC
        LIMIT 200
        """
    )
    by_name: dict[str, dict[str, Any]] = {}
    for row in profile_rows + rows:
        name = store.text(row.get("anchorName"))
        if not name:
            continue
        current = by_name.setdefault(name, {"anchorName": name, "reportCount": 0, "latestAt": ""})
        current["reportCount"] = max(store.to_int(current.get("reportCount"), 0) or 0, store.to_int(row.get("reportCount"), 0) or 0)
        current["latestAt"] = _iso_date(row.get("latestAt") or current.get("latestAt"))
    anchors = sorted(by_name.values(), key=lambda item: item.get("latestAt") or "", reverse=True)
    return {"ok": True, "anchors": anchors}


def _load_reports(anchor_name: str, start_date: str, end_date: str, limit: int = 120) -> list[dict[str, Any]]:
    clauses = ["created_at >= %s", "created_at <= DATE_ADD(%s, INTERVAL 1 DAY)"]
    args: list[Any] = [start_date, end_date]
    if anchor_name and anchor_name != "all":
        clauses.append("anchor_name = %s")
        args.append(anchor_name)
    rows = db.fetch_all(
        f"""
        SELECT id, anchor_name, title, summary, markdown, raw, created_at
        FROM finvue_analysis_reports
        WHERE {" AND ".join(clauses)}
        ORDER BY created_at ASC
        LIMIT %s
        """,
        (*args, limit),
    )
    reports = []
    for row in rows:
        raw = store.parse_json(row.get("raw"), {})
        if not isinstance(raw, dict):
            raw = {}
        reports.append(
            {
                "id": store.text(row.get("id") or raw.get("id")),
                "anchorName": store.text(row.get("anchor_name") or raw.get("anchorName")),
                "title": store.text(row.get("title") or raw.get("title") or raw.get("reportTitle")),
                "summary": store.text(row.get("summary") or raw.get("summary") or raw.get("conclusion")),
                "markdown": store.text(row.get("markdown") or raw.get("markdown") or raw.get("content")),
                "liveTheme": store.text(raw.get("liveTheme") or raw.get("theme")),
                "createdAt": _iso_date(row.get("created_at") or raw.get("analyzedAt")),
                "raw": raw,
            }
        )
    return reports


def _candidate_targets(settings: dict[str, Any]) -> list[dict[str, Any]]:
    names = tushare_market.get_stock_name_map()
    targets = list(THEME_TARGETS)
    for code in tushare_market.normalize_codes(settings.get("indexCodes"), tushare_market.DEFAULT_INDEX_CODES):
        name = tushare_market.INDEX_NAMES.get(code, code)
        targets.append({"name": name, "code": code, "api": "index_daily", "keywords": [name, code, code.split(".")[0]]})
    for code in tushare_market.normalize_codes(settings.get("stockCodes"), tushare_market.DEFAULT_STOCK_CODES):
        name = names.get(code, code)
        targets.append({"name": name, "code": code, "api": "daily", "keywords": [name, code, code.split(".")[0]]})
    dedup: dict[str, dict[str, Any]] = {}
    for item in targets:
        key = f"{item['api']}:{item['code']}"
        if key in dedup:
            dedup[key]["keywords"] = list(dict.fromkeys(dedup[key]["keywords"] + item["keywords"]))
        else:
            dedup[key] = item
    return list(dedup.values())


def _match_target(text_blob: str, targets: list[dict[str, Any]]) -> dict[str, Any] | None:
    lower = text_blob.lower()
    best: tuple[int, dict[str, Any]] | None = None
    for item in targets:
        score = 0
        for keyword in item.get("keywords") or []:
            kw = str(keyword or "").strip()
            if kw and kw.lower() in lower:
                score += max(1, len(kw))
        if score and (best is None or score > best[0]):
            best = (score, item)
    return best[1] if best else None


def _direction(text_blob: str) -> str:
    positive = sum(1 for word in POSITIVE_WORDS if word in text_blob)
    negative = sum(1 for word in NEGATIVE_WORDS if word in text_blob)
    if positive > negative:
        return "看多"
    if negative > positive:
        return "看空"
    return "观察"


def _history_for(target: dict[str, Any], settings: dict[str, Any], start_date: str, end_date: str, cache: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    key = f"{target['api']}:{target['code']}:{start_date}:{end_date}"
    if key in cache:
        return cache[key]
    token = str(settings.get("token") or "").strip()
    if not token:
        cache[key] = []
        return []
    name_map = tushare_market.INDEX_NAMES if target.get("api") == "index_daily" else tushare_market.get_stock_name_map()
    try:
        cache[key] = tushare_market.fetch_history_quotes(
            target.get("api") or "daily",
            token,
            target.get("code") or "",
            _api_date(start_date),
            _api_date(end_date),
            name_map,
        )
    except Exception:
        cache[key] = []
    return cache[key]


def _window_return(quotes: list[dict[str, Any]], report_date: str, horizon: int = 5) -> tuple[float | None, str, str]:
    if not quotes:
        return None, "", ""
    compact_date = _api_date(report_date)
    start_index = 0
    for idx, quote in enumerate(quotes):
        if str(quote.get("tradeDate") or "") >= compact_date:
            start_index = idx
            break
    end_index = min(len(quotes) - 1, start_index + horizon)
    start = quotes[start_index]
    end = quotes[end_index]
    start_close = float(start.get("close") or 0)
    end_close = float(end.get("close") or 0)
    if not start_close:
        return None, str(start.get("tradeDate") or ""), str(end.get("tradeDate") or "")
    return (end_close - start_close) / start_close * 100, str(start.get("tradeDate") or ""), str(end.get("tradeDate") or "")


def _verdict(direction: str, pct: float | None) -> tuple[str, str, int]:
    if pct is None or direction == "观察":
        return "观察", "缺少明确方向，保留为复盘样本", 0
    if direction == "看多" and pct >= 0.2:
        return "验证", "方向与后续 5 个交易日走势一致", 1
    if direction == "看空" and pct <= -0.2:
        return "验证", "风险提示与后续 5 个交易日走势一致", 1
    if abs(pct) < 0.2:
        return "部分", "后续波动较小，方向信号不明显", 0
    return "未验证", "后续走势与观点方向相反", 0


def run_backtest(payload: dict[str, Any]) -> dict[str, Any]:
    end_date = store.text(payload.get("endDate")) or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    start_date = store.text(payload.get("startDate")) or _days_ago(180)
    anchor_name = store.text(payload.get("anchorName") or payload.get("anchor")) or "all"
    settings = tushare_market.get_settings()
    reports = _load_reports(anchor_name, start_date, end_date)
    targets = _candidate_targets(settings)
    history_cache: dict[str, list[dict[str, Any]]] = {}
    details = []
    correct = 0
    matched = 0
    trend: list[float] = []

    history_start = (datetime.strptime(start_date, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
    history_end = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=14)).strftime("%Y-%m-%d")

    for report in reports:
        text_blob = " ".join([report.get("title", ""), report.get("liveTheme", ""), report.get("summary", ""), report.get("markdown", "")[:2400]])
        target = _match_target(text_blob, targets)
        direction = _direction(text_blob)
        if not target:
            details.append(
                {
                    "date": report.get("createdAt"),
                    "anchorName": report.get("anchorName"),
                    "title": report.get("title") or "未命名报告",
                    "target": "未命中行情标的",
                    "direction": direction,
                    "returnPct": None,
                    "verdict": "观察",
                    "conclusion": "报告未命中已配置股票/指数或常见主题关键词",
                }
            )
            continue
        quotes = _history_for(target, settings, history_start, history_end, history_cache)
        return_pct, from_date, to_date = _window_return(quotes, report.get("createdAt") or start_date)
        verdict, conclusion, is_correct = _verdict(direction, return_pct)
        matched += 1 if return_pct is not None and direction != "观察" else 0
        correct += is_correct
        score = 8.8 if verdict == "验证" else 7.8 if verdict == "部分" else 6.8 if verdict == "未验证" else 7.2
        trend.append(score)
        details.append(
            {
                "date": report.get("createdAt"),
                "anchorName": report.get("anchorName"),
                "title": report.get("title") or report.get("liveTheme") or "未命名报告",
                "target": f"{target.get('name')} {target.get('code')}",
                "direction": direction,
                "returnPct": return_pct,
                "fromDate": _iso_date(from_date),
                "toDate": _iso_date(to_date),
                "verdict": verdict,
                "score": score,
                "conclusion": conclusion,
            }
        )

    validation_rate = round(correct / matched * 100, 1) if matched else 0
    coverage_rate = round(len([item for item in details if item.get("target") != "未命中行情标的"]) / len(details) * 100, 1) if details else 0
    avg_score = round(sum(trend) / len(trend), 1) if trend else 0
    return {
        "ok": True,
        "params": {"anchorName": anchor_name, "startDate": start_date, "endDate": end_date},
        "summary": {
            "avgScore": avg_score,
            "validationRate": validation_rate,
            "coverageRate": coverage_rate,
            "reportCount": len(reports),
            "matchedCount": matched,
            "configured": bool(settings.get("token")),
        },
        "trend": trend[-12:],
        "details": details[-80:],
    }
