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
    prompt = f"""下面是本轮热搜和已有 AI 总览。请只判断哪些内容对应 A 股市场里的高热度板块/产业主题。

已有 AI 总览：
{summary_text or "无"}

热搜列表：
{chr(10).join(lines)}

只输出 JSON，不要输出 Markdown，不要输出解释文字。字段格式：
{{
  "themes": [
    {{
      "theme": "板块或产业主题名称，8字以内",
      "keywords": ["能代表该板块热度的关键词，不要泛化"],
      "industries": ["可能关联的 TuShare 行业名或上级行业，少而准"],
      "excludeKeywords": ["容易误伤、需要排除的关键词"],
      "reason": "为什么这个板块有热度，30字以内",
      "heatLevel": "高/中/低",
      "confidence": 0-100
    }}
  ],
  "noiseKeywords": ["娱乐、体育、社会趣闻等应忽略关键词"]
}}

要求：
1. 只能抽取热搜中有事实依据的主题，不要为了凑数扩展到泛行业。
2. 不要识别或输出具体公司、品牌、股票名称，只识别板块/产业主题。
3. 没有明确关联时 themes 可以少于 5 条。
4. 不要输出任何股票买卖建议、涨跌预测或收益暗示。"""
    result = ai_router.generate(
        {
            "systemPrompt": "你是财经新闻结构化分析助手，只识别热搜对应的市场板块和产业主题，不识别个股，不做荐股。",
            "userPrompt": prompt,
            "timeoutSeconds": 25,
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
                "excludeKeywords": [_text(word) for word in (item.get("excludeKeywords") or []) if _text(word)][:8],
                "reason": _text(item.get("reason")),
                "heatLevel": _text(item.get("heatLevel") or item.get("heat_level")),
                "confidence": min(100, max(0, store.to_int(item.get("confidence"), 70) or 70)),
                "source": "ai",
                "matchedKeywords": keywords[:8],
            }
        )
    return {
        "themes": cleaned,
        "noiseKeywords": [_text(word) for word in (data.get("noiseKeywords") or []) if _text(word)][:20],
        "aiMeta": result.get("aiMeta"),
    }


def _industry_matches(industry: str, industries: list[str]) -> bool:
    blob = _text(industry)
    return any(word and word in blob for word in industries)


def _hot_value_score(value: Any) -> float:
    raw = _text(value).replace(",", "")
    number_match = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not number_match:
        return 0.0
    try:
        number = float(number_match.group(0))
    except Exception:
        return 0.0
    if "万" in raw:
        number *= 10000
    if "亿" in raw:
        number *= 100000000
    return min(22.0, max(0.0, len(str(int(abs(number)))) * 2.2))


def _hotspot_weight(item: dict[str, Any]) -> float:
    rank = store.to_int(item.get("rank"), 999) or 999
    rank_score = max(0.0, 36.0 - min(rank, 50) * 0.7)
    platform = _text(item.get("platform"))
    platform_score = {
        "cls": 12.0,
        "wallstreetcn": 12.0,
        "baidu": 8.0,
        "toutiao": 7.0,
        "weibo": 6.0,
        "zhihu": 5.0,
        "douyin": 4.0,
        "bilibili": 4.0,
    }.get(platform, 3.0)
    return rank_score + platform_score + _hot_value_score(item.get("hot_value"))


def _theme_words(theme: dict[str, Any]) -> list[str]:
    words = []
    for key in ("matchedKeywords", "keywords"):
        for word in theme.get(key) or []:
            text = _text(word)
            if text and text not in words:
                words.append(text)
    return words


def _evidence_for_theme(theme: dict[str, Any], hotspots: list[dict[str, Any]], limit: int = 5) -> tuple[list[dict[str, Any]], float]:
    words = _theme_words(theme)
    excludes = [_text(word).lower() for word in (theme.get("excludeKeywords") or []) if _text(word)]
    evidence: list[dict[str, Any]] = []
    score = 0.0
    for item in hotspots:
        title = _text(item.get("title"))
        title_lower = title.lower()
        if not title or any(word and word in title_lower for word in excludes):
            continue
        matched = [word for word in words if word and word.lower() in title_lower]
        if not matched:
            continue
        weight = _hotspot_weight(item) + min(12, len(matched) * 4)
        score += weight
        evidence.append(
            {
                "platform": item.get("platform"),
                "title": title,
                "rank": item.get("rank") or 0,
                "url": item.get("url") or "",
                "hotValue": item.get("hot_value") or "",
                "matchedKeywords": matched[:4],
                "weight": round(weight, 1),
            }
        )
        if len(evidence) >= limit:
            break
    return evidence, score


def _evidence_for(stock: dict[str, Any], theme: dict[str, Any] | None, hotspots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    name = _text(stock.get("name"))
    words = [name] if name else []
    if theme:
        words += _theme_words(theme)
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


def _theme_rule_match(theme: dict[str, Any], rule: dict[str, Any]) -> bool:
    haystack = " ".join(
        [
            _text(theme.get("theme")),
            " ".join(_text(word) for word in (theme.get("keywords") or [])),
            " ".join(_text(word) for word in (theme.get("industries") or [])),
        ]
    ).lower()
    needles = [
        _text(rule.get("theme")),
        *[_text(word) for word in (rule.get("keywords") or [])],
        *[_text(word) for word in (rule.get("industries") or [])],
    ]
    return any(word and (word.lower() in haystack or haystack in word.lower()) for word in needles)


def _matched_rule_for_theme(theme: dict[str, Any], rule_themes: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((rule for rule in rule_themes if _theme_rule_match(theme, rule)), None) or next(
        (rule for rule in THEME_RULES if _theme_rule_match(theme, rule)),
        None,
    )


def _theme_heat_score(theme: dict[str, Any], evidence_score: float, evidence_count: int) -> int:
    confidence = store.to_int(theme.get("confidence"), 68) or 68
    heat_level = _text(theme.get("heatLevel"))
    heat_bonus = {"高": 18, "中": 9, "低": 2}.get(heat_level, 6)
    score = evidence_score * 0.75 + confidence * 0.32 + heat_bonus + evidence_count * 5
    return min(99, max(35, int(round(score))))


def _stock_candidate_for_theme(
    stock: dict[str, Any],
    theme: dict[str, Any],
    text_blob: str,
    leader_codes: set[str],
) -> dict[str, Any] | None:
    code = _text(stock.get("code")).upper()
    name = _text(stock.get("name"))
    industry = _text(stock.get("industry"))
    if not code or not name:
        return None

    score = 0
    reasons: list[str] = []
    relation_type = ""
    if name and name in text_blob:
        score += 95
        relation_type = "直接提及"
        reasons.append(f"热搜直接提到「{name}」")
    if code in leader_codes:
        score += 50
        relation_type = relation_type or "板块代表"
        reasons.append(f"{theme['theme']}代表观察标的")
    if _industry_matches(industry, theme.get("industries") or []):
        score += 44 if theme.get("source") == "ai" else 12
        relation_type = relation_type or "行业映射"
        reasons.append(f"行业「{industry or '未分类'}」映射到{theme['theme']}")
    if score < 40:
        return None
    if theme.get("reason"):
        reasons.append(f"AI判断：{theme.get('reason')}")
    return {
        "code": code,
        "name": name,
        "industry": industry or "未分类",
        "area": stock.get("area") or "",
        "theme": theme.get("theme"),
        "score": score,
        "confidence": min(95, 30 + score),
        "relationType": relation_type or "板块关联",
        "aiReason": theme.get("reason") or "",
        "aiThemeConfidence": theme.get("confidence"),
        "reasons": list(dict.fromkeys(reasons))[:3],
    }


def _build_sector_radar(
    themes: list[dict[str, Any]],
    rule_themes: list[dict[str, Any]],
    stocks: list[dict[str, Any]],
    hotspots: list[dict[str, Any]],
    settings: dict[str, Any],
    text_blob: str,
    quote_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    name_map = tushare_market.get_stock_name_map()
    sectors: list[dict[str, Any]] = []
    flattened: dict[str, dict[str, Any]] = {}
    remaining_quotes = quote_limit

    for theme in themes[:8]:
        if not theme.get("theme"):
            continue
        evidence, evidence_score = _evidence_for_theme(theme, hotspots)
        matched_rule = _matched_rule_for_theme(theme, rule_themes)
        leader_codes = set(theme.get("leaders") or (matched_rule or {}).get("leaders") or [])
        candidates: list[dict[str, Any]] = []

        for stock in stocks:
            candidate = _stock_candidate_for_theme(stock, theme, text_blob, leader_codes)
            if candidate:
                candidates.append(candidate)

        existing_codes = {item["code"] for item in candidates}
        for code in list(leader_codes)[:8]:
            if code in existing_codes:
                continue
            name = name_map.get(code, code)
            candidates.append(
                {
                    "code": code,
                    "name": name,
                    "industry": "板块代表",
                    "area": "",
                    "theme": theme.get("theme"),
                    "score": 45,
                    "confidence": 72,
                    "relationType": "板块代表",
                    "aiReason": theme.get("reason") or "",
                    "aiThemeConfidence": theme.get("confidence"),
                    "reasons": [item for item in [f"{theme['theme']}代表观察标的", theme.get("reason") and f"AI判断：{theme.get('reason')}"] if item],
                }
            )
            existing_codes.add(code)

        candidates = sorted(candidates, key=lambda item: (-item["score"], item["code"]))[:6]
        for item in candidates:
            item["evidence"] = _evidence_for(item, theme, hotspots)
            if remaining_quotes > 0:
                quote = _latest_quote(settings, item["code"], item["name"])
                if quote:
                    item["quote"] = quote
                remaining_quotes -= 1
            previous = flattened.get(item["code"])
            if not previous or item["score"] > previous["score"]:
                flattened[item["code"]] = item

        sectors.append(
            {
                "theme": theme.get("theme"),
                "keywords": _theme_words(theme)[:8],
                "industries": theme.get("industries") or [],
                "reason": theme.get("reason") or "",
                "heatLevel": theme.get("heatLevel") or "",
                "confidence": theme.get("confidence"),
                "heatScore": _theme_heat_score(theme, evidence_score, len(evidence)),
                "evidenceCount": len(evidence),
                "evidence": evidence,
                "stocks": candidates,
                "source": "ai" if theme.get("source") == "ai" else "rule",
            }
        )

    sectors = sorted(
        sectors,
        key=lambda item: (-int(item.get("heatScore") or 0), -int(item.get("evidenceCount") or 0), item.get("theme") or ""),
    )
    items = sorted(flattened.values(), key=lambda item: (-item["score"], -len(item.get("evidence") or []), item["code"]))
    return sectors, items


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
    sectors, ranked = _build_sector_radar(themes, rule_themes, stocks, hotspots, settings, text_blob, quote_limit)
    ranked = ranked[:limit]
    return {
        "ok": True,
        "items": ranked,
        "sectors": sectors,
        "themes": [{"theme": item["theme"], "keywords": item.get("matchedKeywords", [])} for item in themes],
        "aiInsights": {
            "themes": [
                {
                    "theme": item.get("theme"),
                    "keywords": item.get("keywords") or item.get("matchedKeywords") or [],
                    "industries": item.get("industries") or [],
                    "excludeKeywords": item.get("excludeKeywords") or [],
                    "reason": item.get("reason") or "",
                    "heatLevel": item.get("heatLevel") or "",
                    "confidence": item.get("confidence"),
                }
                for item in ai_themes
            ],
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
