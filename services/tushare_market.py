from __future__ import annotations

import requests
from datetime import datetime, timedelta, timezone
from typing import Any

import store


TUSHARE_API_URL = "http://api.tushare.pro"
DEFAULT_INDEX_CODES = ["000001.SH", "399001.SZ", "399006.SZ", "000300.SH", "000905.SH"]
DEFAULT_STOCK_CODES = ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "600036.SH"]
DEFAULT_STOCK_UNIVERSE_LIMIT = 8000
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
SECTOR_LEADERS = {
    "金融地产": {
        "keywords": ["银行", "保险", "证券", "券商", "房地产", "多元金融"],
        "leaders": [
            {"code": "600036.SH", "name": "招商银行"},
            {"code": "601318.SH", "name": "中国平安"},
            {"code": "000001.SZ", "name": "平安银行"},
        ],
    },
    "白酒消费": {
        "keywords": ["白酒", "食品", "饮料", "消费", "零售", "旅游", "家电"],
        "leaders": [
            {"code": "600519.SH", "name": "贵州茅台"},
            {"code": "000858.SZ", "name": "五粮液"},
            {"code": "000333.SZ", "name": "美的集团"},
        ],
    },
    "新能源车": {
        "keywords": ["电池", "新能源", "汽车", "锂电", "光伏", "电气设备"],
        "leaders": [
            {"code": "300750.SZ", "name": "宁德时代"},
            {"code": "002594.SZ", "name": "比亚迪"},
            {"code": "601012.SH", "name": "隆基绿能"},
        ],
    },
    "半导体": {
        "keywords": ["半导体", "芯片", "集成电路", "电子", "元件"],
        "leaders": [
            {"code": "688981.SH", "name": "中芯国际"},
            {"code": "002371.SZ", "name": "北方华创"},
            {"code": "688012.SH", "name": "中微公司"},
        ],
    },
    "医药生物": {
        "keywords": ["医药", "医疗", "生物", "制药", "创新药"],
        "leaders": [
            {"code": "600276.SH", "name": "恒瑞医药"},
            {"code": "300760.SZ", "name": "迈瑞医疗"},
            {"code": "603259.SH", "name": "药明康德"},
        ],
    },
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
        "configured": bool(raw.get("token")),
        "schedulerEnabled": bool(raw.get("enabled") and raw.get("token")),
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


def _stock_name_map() -> dict[str, str]:
    universe = store.safe_object(store.get_kv("tushare-stock-universe", {}))
    items = universe.get("items") if isinstance(universe.get("items"), list) else []
    names = {
        str(item.get("code") or "").upper(): str(item.get("name") or "").strip()
        for item in items
        if item.get("code") and item.get("name")
    }
    return {**STOCK_NAMES, **names}


def get_stock_name_map() -> dict[str, str]:
    return _stock_name_map()


def fetch_history_quotes(
    api_name: str,
    token: str,
    code: str,
    start_date: str,
    end_date: str,
    name_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    rows = _request(
        api_name,
        token,
        {"ts_code": code, "start_date": start_date, "end_date": end_date},
        "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
    )
    names = name_map or (_stock_name_map() if api_name == "daily" else INDEX_NAMES)
    quotes = [
        {
            "code": code,
            "name": names.get(code, code),
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
        for row in rows
    ]
    return sorted(quotes, key=lambda item: str(item.get("tradeDate") or ""))


def fetch_stock_universe(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    token = str(cfg.get("token") or "").strip()
    if not token:
        raise RuntimeError("TuShare token 未配置")
    rows = _request(
        "stock_basic",
        token,
        {"list_status": "L"},
        "ts_code,symbol,name,area,industry,market,exchange,list_date",
    )
    items = []
    for row in rows[:DEFAULT_STOCK_UNIVERSE_LIMIT]:
        code = str(row.get("ts_code") or "").upper()
        if not code:
            continue
        items.append(
            {
                "code": code,
                "symbol": row.get("symbol"),
                "name": row.get("name"),
                "area": row.get("area"),
                "industry": row.get("industry") or "未分类",
                "market": row.get("market"),
                "exchange": row.get("exchange"),
                "listDate": row.get("list_date"),
            }
        )
    items.sort(key=lambda item: str(item.get("code") or ""))
    payload = {"updatedAt": _now_iso(), "count": len(items), "items": items}
    store.set_kv("tushare-stock-universe", payload)
    return payload


def get_stock_universe() -> dict[str, Any]:
    return store.safe_object(store.get_kv("tushare-stock-universe", {}))


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


def _stock_meta_map() -> dict[str, dict[str, Any]]:
    universe = store.safe_object(store.get_kv("tushare-stock-universe", {}))
    items = universe.get("items") if isinstance(universe.get("items"), list) else []
    return {str(item.get("code") or "").upper(): item for item in items if item.get("code")}


def _classify_sector(stock: dict[str, Any], meta: dict[str, Any] | None = None) -> str:
    text_blob = " ".join(
        str(value or "")
        for value in (
            stock.get("name"),
            stock.get("code"),
            (meta or {}).get("industry"),
            (meta or {}).get("market"),
        )
    )
    for sector, rule in SECTOR_LEADERS.items():
        if any(keyword and keyword in text_blob for keyword in rule["keywords"]):
            return sector
    return str((meta or {}).get("industry") or "重点观察")


def build_hot_sectors(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    meta_map = _stock_meta_map()
    quote_map = {str(item.get("code") or "").upper(): item for item in stocks}
    grouped: dict[str, list[dict[str, Any]]] = {}
    for stock in stocks:
        code = str(stock.get("code") or "").upper()
        sector = _classify_sector(stock, meta_map.get(code))
        grouped.setdefault(sector, []).append(stock)

    for sector, rule in SECTOR_LEADERS.items():
        leaders = grouped.setdefault(sector, [])
        existing = {str(item.get("code") or "").upper() for item in leaders}
        for leader in rule["leaders"]:
            code = str(leader.get("code") or "").upper()
            if code not in existing:
                leaders.append({**leader, "pending": code not in quote_map, **(quote_map.get(code) or {})})
                existing.add(code)

    sectors = []
    for sector, leaders in grouped.items():
        quoted = [item for item in leaders if not item.get("pending") and item.get("pctChange") is not None]
        avg_pct = sum(float(item.get("pctChange") or 0) for item in quoted) / len(quoted) if quoted else None
        amount = sum(float(item.get("amount") or 0) for item in quoted)
        leaders_sorted = sorted(
            leaders,
            key=lambda item: (
                1 if item.get("pending") else 0,
                -abs(float(item.get("pctChange") or 0)) if item.get("pctChange") is not None else 0,
            ),
        )[:5]
        sectors.append(
            {
                "name": sector,
                "avgPctChange": avg_pct,
                "amount": amount,
                "leaderCount": len(quoted),
                "leaders": leaders_sorted,
            }
        )
    return sorted(
        sectors,
        key=lambda item: (item["leaderCount"] <= 0, -abs(float(item.get("avgPctChange") or 0)), -float(item.get("amount") or 0)),
    )[:8]


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
    stock_names = _stock_name_map()
    stocks = [
        quote
        for code in normalize_codes(cfg.get("stockCodes"), DEFAULT_STOCK_CODES)
        if (quote := _latest_quote("daily", token, code, stock_names))
    ]
    snapshot = {
        "source": "tushare",
        "updatedAt": _now_iso(),
        "indexes": indexes,
        "stocks": stocks,
        "hotSectors": build_hot_sectors(stocks),
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
