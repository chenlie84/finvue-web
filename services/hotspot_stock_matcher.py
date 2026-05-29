from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import db
import store
from services import tushare_market


THEME_RULES = [
    {
        "theme": "AI算力/半导体",
        "keywords": ["AI", "算力", "服务器", "DeepSeek", "芯片", "半导体", "存储", "光模块", "CPO", "PCB", "英伟达", "戴尔"],
        "industries": ["半导体", "元器件", "通信设备", "电脑设备", "软件服务", "互联网"],
        "leaders": ["688981.SH", "002371.SZ", "688012.SH", "600584.SH", "300308.SZ", "000977.SZ", "002463.SZ"],
    },
    {
        "theme": "新能源车/智能驾驶",
        "keywords": ["电车", "新能源车", "新能源汽车", "智能驾驶", "比亚迪", "养路费", "电池", "锂电", "充电桩"],
        "industries": ["汽车", "电气设备", "电池", "小金属", "汽车配件"],
        "leaders": ["300750.SZ", "002594.SZ", "601012.SH", "002466.SZ", "002460.SZ", "002452.SZ"],
    },
    {
        "theme": "城市更新/基建",
        "keywords": ["城市更新", "老旧小区", "地下管网", "基建", "水利", "地产", "住房", "建筑"],
        "industries": ["建筑工程", "建筑", "水务", "工程机械", "房地产", "建材"],
        "leaders": ["601668.SH", "601390.SH", "601186.SH", "600048.SH", "000002.SZ", "000425.SZ"],
    },
    {
        "theme": "通胀/利率/金融",
        "keywords": ["PCE", "通胀", "美联储", "降息", "利率", "美元", "国债", "汇率"],
        "industries": ["银行", "证券", "保险", "多元金融", "黄金"],
        "leaders": ["600036.SH", "601318.SH", "000001.SZ", "600030.SH", "600547.SH"],
    },
    {
        "theme": "地缘/能源/军工",
        "keywords": ["美伊", "停火", "霍尔木兹", "原油", "石油", "天然气", "军工", "国防", "中东"],
        "industries": ["石油", "石油开采", "化工", "航空", "船舶", "国防军工", "军工"],
        "leaders": ["601857.SH", "600028.SH", "600938.SH", "600150.SH", "600760.SH"],
    },
    {
        "theme": "机器人",
        "keywords": ["机器人", "人形机器人", "具身智能", "减速器", "自动化"],
        "industries": ["机械基件", "专用机械", "电气设备", "工业机械", "自动化设备"],
        "leaders": ["300124.SZ", "002050.SZ", "688017.SH", "002747.SZ"],
    },
    {
        "theme": "消费电子",
        "keywords": ["手机", "AI眼镜", "消费电子", "苹果", "小米", "电子产品", "4nm"],
        "industries": ["元器件", "消费电子", "通信设备", "半导体"],
        "leaders": ["002475.SZ", "000725.SZ", "002241.SZ", "300433.SZ"],
    },
]


def _recent_hotspots(limit: int = 120) -> list[dict[str, Any]]:
    return db.fetch_all(
        """
        SELECT platform, title, url, `rank`, hot_value, last_seen_at
        FROM finvue_hotspot_items
        WHERE last_seen_at >= DATE_SUB(NOW(), INTERVAL 2 HOUR)
        ORDER BY
          CASE WHEN `rank` IS NULL OR `rank` = 0 THEN 999 ELSE `rank` END ASC,
          last_seen_at DESC
        LIMIT %s
        """,
        (limit,),
    )


def _text(value: Any) -> str:
    return str(value or "").strip()


def _stock_universe(settings: dict[str, Any]) -> list[dict[str, Any]]:
    universe = tushare_market.get_stock_universe()
    items = universe.get("items") if isinstance(universe.get("items"), list) else []
    if items:
        return items
    if settings.get("token"):
        try:
            universe = tushare_market.fetch_stock_universe(settings)
            return universe.get("items") if isinstance(universe.get("items"), list) else []
        except Exception:
            return []
    return []


def _theme_hits(text_blob: str) -> list[dict[str, Any]]:
    lower = text_blob.lower()
    hits = []
    for rule in THEME_RULES:
        words = [word for word in rule["keywords"] if word and word.lower() in lower]
        if words:
            hits.append({**rule, "matchedKeywords": words})
    return hits


def _industry_matches(industry: str, industries: list[str]) -> bool:
    blob = _text(industry)
    return any(word and word in blob for word in industries)


def _evidence_for(stock: dict[str, Any], theme: dict[str, Any] | None, hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    name = _text(stock.get("name"))
    words = [name] if name else []
    if theme:
        words += theme.get("matchedKeywords") or theme.get("keywords") or []
    evidence = []
    for item in hotspots:
        title = _text(item.get("title"))
        if any(word and word.lower() in title.lower() for word in words):
            evidence.append(
                {
                    "platform": item.get("platform"),
                    "title": title,
                    "rank": item.get("rank") or 0,
                    "url": item.get("url") or "",
                }
            )
        if len(evidence) >= 3:
            break
    return evidence


def _latest_quote(settings: dict[str, Any], code: str, name: str) -> dict[str, Any] | None:
    token = _text(settings.get("token"))
    if not token:
        return None
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=20)).strftime("%Y%m%d")
    try:
        rows = tushare_market.fetch_history_quotes("daily", token, code, start, end, {code: name})
    except Exception:
        return None
    return rows[-1] if rows else None


def match_related_stocks(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = store.safe_object(payload)
    summary_text = _text(body.get("summary") or body.get("analysis"))
    limit = min(30, max(8, store.to_int(body.get("limit"), 18) or 18))
    quote_limit = min(18, max(0, store.to_int(body.get("quoteLimit"), 12) or 12))
    settings = tushare_market.get_settings()
    hotspots = _recent_hotspots()
    if not hotspots and not summary_text:
        return {"ok": True, "items": [], "themes": [], "hotspotCount": 0, "universeCount": 0, "generatedAt": datetime.now().isoformat()}

    title_blob = "\n".join(_text(item.get("title")) for item in hotspots)
    text_blob = f"{summary_text}\n{title_blob}"
    themes = _theme_hits(text_blob)
    leader_codes = {code for theme in themes for code in theme.get("leaders", [])}
    stocks = _stock_universe(settings)
    by_code: dict[str, dict[str, Any]] = {}

    for stock in stocks:
        code = _text(stock.get("code")).upper()
        name = _text(stock.get("name"))
        industry = _text(stock.get("industry"))
        if not code or not name:
            continue
        score = 0
        reasons: list[str] = []
        matched_theme = None
        if name and name in text_blob:
            score += 90
            reasons.append(f"热搜直接提到「{name}」")
        for theme in themes:
            if code in theme.get("leaders", []):
                score += 42
                matched_theme = matched_theme or theme
                reasons.append(f"{theme['theme']}核心/常用观察标的")
            elif _industry_matches(industry, theme.get("industries") or []):
                score += 22
                matched_theme = matched_theme or theme
                reasons.append(f"行业「{industry or '未分类'}」命中{theme['theme']}")
        if not score:
            continue
        by_code[code] = {
            "code": code,
            "name": name,
            "industry": industry or "未分类",
            "area": stock.get("area") or "",
            "theme": (matched_theme or {}).get("theme") or "直接命中",
            "score": score,
            "confidence": min(95, 38 + score),
            "reasons": list(dict.fromkeys(reasons))[:3],
            "evidence": _evidence_for(stock, matched_theme, hotspots),
        }

    for theme in themes:
        for code in theme.get("leaders", []):
            if code in by_code:
                continue
            name = tushare_market.get_stock_name_map().get(code, code)
            by_code[code] = {
                "code": code,
                "name": name,
                "industry": "主题龙头",
                "area": "",
                "theme": theme.get("theme"),
                "score": 36,
                "confidence": 74,
                "reasons": [f"{theme['theme']}常用观察标的"],
                "evidence": _evidence_for({"code": code, "name": name}, theme, hotspots),
            }

    ranked = sorted(by_code.values(), key=lambda item: (-item["score"], -len(item.get("evidence") or []), item["code"]))[:limit]
    for item in ranked[:quote_limit]:
        quote = _latest_quote(settings, item["code"], item["name"])
        if quote:
            item["quote"] = quote
    return {
        "ok": True,
        "items": ranked,
        "themes": [{"theme": item["theme"], "keywords": item.get("matchedKeywords", [])} for item in themes],
        "hotspotCount": len(hotspots),
        "universeCount": len(stocks),
        "generatedAt": datetime.now().isoformat(),
        "hasToken": bool(settings.get("token")),
    }
