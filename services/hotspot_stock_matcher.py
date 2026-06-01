from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

import ai_router
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
        "industries": ["汽车", "电池", "小金属", "汽车配件"],
        "leaders": ["300750.SZ", "002594.SZ", "601012.SH", "002466.SZ", "002460.SZ"],
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


def _json_from_ai(text: str) -> dict[str, Any]:
    raw = _text(text)
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.I)
    if fenced:
        raw = fenced.group(1).strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    parsed = json.loads(raw)
    return store.safe_object(parsed)


def _ai_theme_context(summary_text: str, hotspots: list[dict[str, Any]], username: str = "") -> dict[str, Any]:
    lines = []
    for item in hotspots[:80]:
        rank = item.get("rank") or "-"
        hot = f"｜热度 {item.get('hot_value')}" if item.get("hot_value") else ""
        lines.append(f"- [{item.get('platform')} #{rank}] {_text(item.get('title'))}{hot}")
    prompt = f"""下面是本轮热搜和已有 AI 总览。请先判断哪些内容和 A 股股票库可能有关联，再抽取结构化主题。

已有 AI 总览：
{summary_text or "无"}

热搜列表：
{chr(10).join(lines)}

只输出 JSON，不要输出 Markdown，不要输出解释文字。字段格式：
{{
  "themes": [
    {{
      "theme": "主题名称，8字以内",
      "keywords": ["能代表事件/产业链的关键词，不要泛化"],
      "industries": ["可能关联的 TuShare 行业名或上级行业，少而准"],
      "directCompanies": ["热搜明确提到的公司名或品牌名"],
      "excludeKeywords": ["容易误伤、需要排除的关键词"],
      "reason": "为什么这个主题值得关注，30字以内",
      "confidence": 0-100
    }}
  ],
  "explicitCompanies": ["热搜明确提到的公司/品牌"],
  "noiseKeywords": ["娱乐、体育、社会趣闻等应忽略关键词"]
}}

要求：
1. 只能抽取热搜中有事实依据的主题，不要为了凑数扩展到泛行业。
2. 没有明确关联时 themes 可以少于 5 条。
3. 不要输出任何股票买卖建议、涨跌预测或收益暗示。"""
    result = ai_router.generate(
        {
            "systemPrompt": "你是财经新闻结构化分析助手，只做信息抽取和产业链主题识别，不做荐股。",
            "userPrompt": prompt,
        },
        username=username,
    )
    data = _json_from_ai(result.get("markdown") or "")
    themes = data.get("themes") if isinstance(data.get("themes"), list) else []
    cleaned = []
    for item in themes[:8]:
        if not isinstance(item, dict):
            continue
        theme = _text(item.get("theme"))
        keywords = [_text(word) for word in (item.get("keywords") or []) if _text(word)]
        if not theme or not keywords:
            continue
        cleaned.append(
            {
                "theme": theme,
                "keywords": keywords[:8],
                "industries": [_text(word) for word in (item.get("industries") or []) if _text(word)][:6],
                "directCompanies": [_text(word) for word in (item.get("directCompanies") or []) if _text(word)][:8],
                "excludeKeywords": [_text(word) for word in (item.get("excludeKeywords") or []) if _text(word)][:8],
                "reason": _text(item.get("reason")),
                "confidence": min(100, max(0, store.to_int(item.get("confidence"), 70) or 70)),
                "source": "ai",
                "matchedKeywords": keywords[:8],
            }
        )
    return {
        "themes": cleaned,
        "explicitCompanies": [_text(word) for word in (data.get("explicitCompanies") or []) if _text(word)][:20],
        "noiseKeywords": [_text(word) for word in (data.get("noiseKeywords") or []) if _text(word)][:20],
        "aiMeta": result.get("aiMeta"),
    }


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


def _stock_name_hit(name: str, words: list[str], text_blob: str) -> bool:
    if name and name in text_blob:
        return True
    return any(word and (word in name or name in word) for word in words if len(word) >= 2)


def match_related_stocks(payload: dict[str, Any] | None = None, username: str = "") -> dict[str, Any]:
    body = store.safe_object(payload)
    summary_text = _text(body.get("summary") or body.get("analysis"))
    use_ai = body.get("useAi", True) is not False
    limit = min(30, max(8, store.to_int(body.get("limit"), 18) or 18))
    quote_limit = min(18, max(0, store.to_int(body.get("quoteLimit"), 12) or 12))
    settings = tushare_market.get_settings()
    hotspots = _recent_hotspots()
    if not hotspots and not summary_text:
        return {"ok": True, "items": [], "themes": [], "hotspotCount": 0, "universeCount": 0, "generatedAt": datetime.now().isoformat()}

    title_blob = "\n".join(_text(item.get("title")) for item in hotspots)
    text_blob = f"{summary_text}\n{title_blob}"
    ai_context: dict[str, Any] = {}
    ai_error = ""
    if use_ai:
        try:
            ai_context = _ai_theme_context(summary_text, hotspots, username)
        except Exception as exc:
            ai_error = str(exc)
    ai_themes = ai_context.get("themes") if isinstance(ai_context.get("themes"), list) else []
    themes = ai_themes or _theme_hits(text_blob)
    rule_themes = _theme_hits(text_blob)
    stocks = _stock_universe(settings)
    by_code: dict[str, dict[str, Any]] = {}
    explicit_companies = [_text(word) for word in (ai_context.get("explicitCompanies") or []) if _text(word)]

    for stock in stocks:
        code = _text(stock.get("code")).upper()
        name = _text(stock.get("name"))
        industry = _text(stock.get("industry"))
        if not code or not name:
            continue
        score = 0
        reasons: list[str] = []
        matched_theme = None
        relation_type = ""
        if _stock_name_hit(name, explicit_companies, text_blob):
            score += 95
            relation_type = "直接提及"
            reasons.append(f"热搜直接提到「{name}」")
        for theme in themes:
            direct_companies = [_text(word) for word in (theme.get("directCompanies") or []) if _text(word)]
            if _stock_name_hit(name, direct_companies, ""):
                score += 80
                matched_theme = matched_theme or theme
                relation_type = relation_type or "AI直接点名"
                reasons.append(f"AI 从热搜中识别到「{name}」")
            elif code in theme.get("leaders", []):
                score += 50
                matched_theme = matched_theme or theme
                if not relation_type:
                    relation_type = "主题核心"
                reasons.append(f"{theme['theme']}核心观察标的")
            elif _industry_matches(industry, theme.get("industries") or []):
                score += 12 if theme.get("source") == "ai" else 8
                matched_theme = matched_theme or theme
                reasons.append(f"行业「{industry or '未分类'}」弱关联{theme['theme']}")
        if score < 40:
            continue
        if matched_theme and matched_theme.get("source") == "ai" and matched_theme.get("reason"):
            reasons.append(f"AI判断：{matched_theme.get('reason')}")
        by_code[code] = {
            "code": code,
            "name": name,
            "industry": industry or "未分类",
            "area": stock.get("area") or "",
            "theme": (matched_theme or {}).get("theme") or "直接命中",
            "score": score,
            "confidence": min(95, 30 + score),
            "relationType": relation_type or "行业弱关联",
            "aiReason": (matched_theme or {}).get("reason") or "",
            "aiThemeConfidence": (matched_theme or {}).get("confidence"),
            "reasons": list(dict.fromkeys(reasons))[:3],
            "evidence": _evidence_for(stock, matched_theme, hotspots),
        }

    for theme in themes:
        fallback_codes = list(theme.get("leaders") or [])
        if not fallback_codes and theme.get("source") == "ai":
            matched_rule = next(
                (
                    rule for rule in rule_themes
                    if theme.get("theme") in rule.get("theme", "") or rule.get("theme", "") in theme.get("theme", "")
                ),
                None,
            )
            fallback_codes = list((matched_rule or {}).get("leaders") or [])
        for code in fallback_codes:
            if code in by_code:
                continue
            name = tushare_market.get_stock_name_map().get(code, code)
            by_code[code] = {
                "code": code,
                "name": name,
                "industry": "主题龙头",
                "area": "",
                "theme": theme.get("theme"),
                "score": 45,
                "confidence": 75,
                "relationType": "主题核心",
                "aiReason": theme.get("reason") or "",
                "aiThemeConfidence": theme.get("confidence"),
                "reasons": [item for item in [f"{theme['theme']}核心观察标的", theme.get("reason") and f"AI判断：{theme.get('reason')}"] if item],
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
        "aiInsights": {
            "themes": [
                {
                    "theme": item.get("theme"),
                    "keywords": item.get("keywords") or item.get("matchedKeywords") or [],
                    "industries": item.get("industries") or [],
                    "directCompanies": item.get("directCompanies") or [],
                    "excludeKeywords": item.get("excludeKeywords") or [],
                    "reason": item.get("reason") or "",
                    "confidence": item.get("confidence"),
                }
                for item in ai_themes
            ],
            "explicitCompanies": explicit_companies,
            "noiseKeywords": ai_context.get("noiseKeywords") or [],
        },
        "aiUsed": bool(ai_themes),
        "aiError": ai_error,
        "aiMeta": ai_context.get("aiMeta"),
        "hotspotCount": len(hotspots),
        "universeCount": len(stocks),
        "generatedAt": datetime.now().isoformat(),
        "hasToken": bool(settings.get("token")),
    }
