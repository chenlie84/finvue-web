from __future__ import annotations

import requests
from datetime import datetime, timedelta, timezone
from typing import Any

import store


TUSHARE_API_URL = "http://api.tushare.pro"
DEFAULT_INDEX_CODES = ["000001.SH", "399001.SZ", "399006.SZ", "000300.SH", "000905.SH"]
DEFAULT_STOCK_CODES = ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "600036.SH"]
INDEX_NAMES = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
}
STOCK_NAMES = {
    "000001.SZ": "平安银行",
    "600519.SH": "贵州茅台",
    "300750.SZ": "宁德时代",
    "601318.SH": "中国平安",
    "600036.SH": "招商银行",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_codes(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, str):
        items = value.replace("\n", ",").split(",")
    elif isinstance(value, list):
        items = value
    else:
        items = fallback
    result: list[str] = []
    for item in items:
        code = str(item or "").strip().upper()
        if code and code not in result:
            result.append(code)
    return result or fallback


def get_settings() -> dict[str, Any]:
    saved = store.safe_object(store.get_kv("tushare-market-settings", {}))
    return {
        "enabled": bool(saved.get("enabled", False)),
        "token": str(saved.get("token") or ""),
        "intervalMinutes": max(15, store.to_int(saved.get("intervalMinutes"), 60) or 60),
        "indexCodes": normalize_codes(saved.get("indexCodes"), DEFAULT_INDEX_CODES),
        "stockCodes": normalize_codes(saved.get("stockCodes"), DEFAULT_STOCK_CODES),
        "updatedAt": store.text(saved.get("updatedAt")),
        "updatedBy": store.text(saved.get("updatedBy")),
    }


def save_settings(payload: dict[str, Any], username: str = "") -> dict[str, Any]:
    current = get_settings()
    incoming = store.safe_object(payload)
    token = str(incoming.get("token") or "")
    if token == "********":
        token = current.get("token", "")
    value = {
        "enabled": bool(incoming.get("enabled", current.get("enabled", False))),
        "token": token.strip(),
        "intervalMinutes": max(15, store.to_int(incoming.get("intervalMinutes"), current.get("intervalMinutes", 60)) or 60),
        "indexCodes": normalize_codes(incoming.get("indexCodes"), DEFAULT_INDEX_CODES),
        "stockCodes": normalize_codes(incoming.get("stockCodes"), DEFAULT_STOCK_CODES),
        "updatedAt": _now_iso(),
        "updatedBy": store.text(username),
    }
    return store.set_kv("tushare-market-settings", value)


def mask_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = settings or get_settings()
    return {
        key: ("********" if key == "token" and raw.get("token") else value)
        for key, value in raw.items()
        if key != "token"
    } | {
        "token": "********" if raw.get("token") else "",
        "hasToken": bool(raw.get("token")),
        "configured": bool(raw.get("enabled") and raw.get("token")),
    }


def _date_range(days: int = 20) -> tuple[str, str]:
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d")
    return start, end


def _request(api_name: str, token: str, params: dict[str, Any] | None = None, fields: str = "") -> list[dict[str, Any]]:
    response = requests.post(
        TUSHARE_API_URL,
        json={"api_name": api_name, "token": token, "params": params or {}, "fields": fields},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg") or f"TuShare 返回错误：{payload.get('code')}")
    data = payload.get("data") or {}
    columns = data.get("fields") or []
    return [dict(zip(columns, row)) for row in data.get("items") or []]


def _latest_quote(api_name: str, token: str, code: str, name_map: dict[str, str]) -> dict[str, Any] | None:
    start_date, end_date = _date_range()
    rows = _request(
        api_name,
        token,
        {"ts_code": code, "start_date": start_date, "end_date": end_date},
        "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    )
    if not rows:
        return None
    row = sorted(rows, key=lambda item: str(item.get("trade_date") or ""), reverse=True)[0]
    return {
        "code": code,
        "name": name_map.get(code, code),
        "tradeDate": row.get("trade_date"),
        "open": row.get("open"),
        "high": row.get("high"),
        "low": row.get("low"),
        "close": row.get("close"),
        "preClose": row.get("pre_close"),
        "change": row.get("change"),
        "pctChange": row.get("pct_chg"),
        "volume": row.get("vol"),
        "amount": row.get("amount"),
    }


def fetch_market_snapshot(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    token = str(cfg.get("token") or "").strip()
    if not token:
        raise RuntimeError("TuShare token 未配置")
    indexes = [
        quote
        for code in normalize_codes(cfg.get("indexCodes"), DEFAULT_INDEX_CODES)
        if (quote := _latest_quote("index_daily", token, code, INDEX_NAMES))
    ]
    stocks = [
        quote
        for code in normalize_codes(cfg.get("stockCodes"), DEFAULT_STOCK_CODES)
        if (quote := _latest_quote("daily", token, code, STOCK_NAMES))
    ]
    snapshot = {
        "source": "tushare",
        "updatedAt": _now_iso(),
        "indexes": indexes,
        "stocks": stocks,
        "summary": {
            "indexCount": len(indexes),
            "stockCount": len(stocks),
            "tradeDate": (indexes[0] if indexes else stocks[0] if stocks else {}).get("tradeDate", ""),
        },
    }
    store.set_kv("tushare-market-cache", snapshot)
    return snapshot


def get_cached_snapshot() -> dict[str, Any]:
    return store.safe_object(store.get_kv("tushare-market-cache", {}))


def test_token(token: str) -> dict[str, Any]:
    rows = _request(
        "trade_cal",
        token,
        {"exchange": "SSE", "start_date": datetime.now().strftime("%Y%m01"), "end_date": datetime.now().strftime("%Y%m%d")},
        "exchange,cal_date,is_open,pretrade_date",
    )
    return {"ok": True, "rows": len(rows)}
