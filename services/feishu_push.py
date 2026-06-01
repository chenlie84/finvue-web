from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import db
import store
from services import hotspot_fetcher, hotspot_stock_matcher


SETTINGS_KEY = "feishu-hotspot-push-settings"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_settings() -> dict[str, Any]:
    saved = store.safe_object(store.get_kv(SETTINGS_KEY, {}))
    return {
        "enabled": bool(saved.get("enabled", False)),
        "webhookUrl": store.text(saved.get("webhookUrl")),
        "intervalMinutes": max(15, store.to_int(saved.get("intervalMinutes"), 120) or 120),
        "pushRelatedStocks": saved.get("pushRelatedStocks", True) is not False,
        "lastPushedAt": store.text(saved.get("lastPushedAt")),
        "lastStatus": store.text(saved.get("lastStatus")),
        "updatedAt": store.text(saved.get("updatedAt")),
        "updatedBy": store.text(saved.get("updatedBy")),
    }


def mask_settings(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = settings or get_settings()
    webhook = store.text(raw.get("webhookUrl"))
    masked = ""
    if webhook:
        masked = webhook[:36] + "..." + webhook[-8:] if len(webhook) > 52 else "********"
    return {
        **{key: value for key, value in raw.items() if key != "webhookUrl"},
        "webhookUrl": "********" if webhook else "",
        "webhookPreview": masked,
        "configured": bool(webhook),
        "schedulerEnabled": bool(raw.get("enabled") and webhook),
    }


def save_settings(payload: dict[str, Any], username: str = "") -> dict[str, Any]:
    current = get_settings()
    incoming = store.safe_object(payload)
    webhook = store.text(incoming.get("webhookUrl"))
    if webhook == "********":
        webhook = current.get("webhookUrl", "")
    value = {
        **current,
        "enabled": bool(incoming.get("enabled", current.get("enabled", False))),
        "webhookUrl": webhook,
        "intervalMinutes": max(15, store.to_int(incoming.get("intervalMinutes"), current.get("intervalMinutes", 120)) or 120),
        "pushRelatedStocks": incoming.get("pushRelatedStocks", current.get("pushRelatedStocks", True)) is not False,
        "updatedAt": _now_iso(),
        "updatedBy": store.text(username),
    }
    return store.set_kv(SETTINGS_KEY, value)


def _configured_hotspot_platforms() -> list[str]:
    row = db.fetch_one("SELECT enabled_platforms FROM finvue_hotspot_settings WHERE id = 'default'")
    if row and row.get("enabled_platforms"):
        try:
            platforms = json.loads(str(row.get("enabled_platforms") or "[]"))
            if isinstance(platforms, list):
                cleaned = [store.text(item) for item in platforms if store.text(item)]
                if cleaned:
                    return cleaned
        except Exception:
            pass
    return ["weibo", "zhihu", "baidu", "douyin", "bilibili", "toutiao", "cls", "wallstreetcn"]


def refresh_hotspots_before_push() -> dict[str, Any]:
    platforms = _configured_hotspot_platforms()
    try:
        return hotspot_fetcher.fetch_all_platforms(platforms)
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "totalItems": 0,
            "successPlatforms": [],
            "failedPlatforms": [{"platform": "all", "error": str(exc)}],
            "timestamp": _now_iso(),
        }


def _recent_hotspots(limit: int = 8) -> list[dict[str, Any]]:
    try:
        return db.fetch_all(
            """
            SELECT platform, title, `rank`, hot_value, last_seen_at
            FROM finvue_hotspot_items
            WHERE last_seen_at >= DATE_SUB(NOW(), INTERVAL 2 HOUR)
            ORDER BY
              CASE WHEN `rank` IS NULL OR `rank` = 0 THEN 999 ELSE `rank` END ASC,
              last_seen_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    except Exception:
        return []


def _format_quote(item: dict[str, Any]) -> str:
    quote = store.safe_object(item.get("quote"))
    pct = quote.get("pctChange")
    if pct is None or pct == "":
        return "未取行情"
    try:
        value = float(pct)
        return f"{value:+.2f}%"
    except Exception:
        return str(pct)


def _format_ai_insights(related: dict[str, Any]) -> list[str]:
    insights = store.safe_object(related.get("aiInsights"))
    themes = insights.get("themes") if isinstance(insights.get("themes"), list) else []
    if themes:
        lines = []
        for index, item in enumerate(themes[:5], 1):
            theme = store.text(item.get("theme") or "未命名主题")
            keywords = "、".join(store.text(word) for word in (item.get("keywords") or [])[:4] if store.text(word))
            industries = "、".join(store.text(word) for word in (item.get("industries") or [])[:4] if store.text(word))
            reason = store.text(item.get("reason"))
            heat = store.text(item.get("heatLevel"))
            parts = [theme]
            if heat:
                parts.append(f"热度：{heat}")
            if keywords:
                parts.append(f"关键词：{keywords}")
            if industries:
                parts.append(f"映射行业：{industries}")
            if reason:
                parts.append(f"AI判断：{reason}")
            lines.append(f"{index}. " + "｜".join(parts))
        noise = "、".join(store.text(word) for word in (insights.get("noiseKeywords") or [])[:8] if store.text(word))
        if noise:
            lines.append(f"已降权噪音：{noise}")
        return lines

    themes = related.get("themes") if isinstance(related.get("themes"), list) else []
    if themes:
        return ["、".join(str(item.get("theme") or "") for item in themes[:6] if item.get("theme"))]
    if related.get("aiError"):
        return [f"AI主题识别失败，已使用规则兜底：{related.get('aiError')}"]
    return ["暂未识别出明确主题。"]


def _format_sector_radar(related: dict[str, Any]) -> list[str]:
    sectors = related.get("sectors") if isinstance(related.get("sectors"), list) else []
    if not sectors:
        return _format_ai_insights(related)
    lines = []
    for index, sector in enumerate(sectors[:6], 1):
        theme = store.text(sector.get("theme") or "未命名板块")
        score = store.to_int(sector.get("heatScore"), 0) or 0
        reason = store.text(sector.get("reason"))
        keywords = "、".join(store.text(word) for word in (sector.get("keywords") or [])[:5] if store.text(word))
        evidence = sector.get("evidence") if isinstance(sector.get("evidence"), list) else []
        stocks = sector.get("stocks") if isinstance(sector.get("stocks"), list) else []
        first_hit = store.safe_object(evidence[0]) if evidence else {}
        stock_names = "、".join(
            f"{store.text(item.get('name'))}({_format_quote(item)})"
            for item in stocks[:3]
            if store.text(item.get("name"))
        )
        parts = [f"{index}. {theme}", f"热度分 {score}"]
        if keywords:
            parts.append(f"关键词：{keywords}")
        if reason:
            parts.append(f"AI判断：{reason}")
        if first_hit:
            parts.append(f"代表热搜：[{first_hit.get('platform')} #{first_hit.get('rank') or '-'}] {first_hit.get('title')}")
        if stock_names:
            parts.append(f"观察池：{stock_names}")
        lines.append("｜".join(parts))
    return lines


def build_message(settings: dict[str, Any] | None = None, refresh_result: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    hotspots = _recent_hotspots()
    related = (
        hotspot_stock_matcher.match_related_stocks({"limit": 12, "quoteLimit": 4})
        if cfg.get("pushRelatedStocks", True)
        else {"items": [], "themes": []}
    )
    items = related.get("items") or []
    sectors = related.get("sectors") or []
    themes = related.get("themes") or []
    ai_used = bool(related.get("aiUsed"))
    lines = [
        "FinVue 热点板块雷达",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        _format_refresh_line(refresh_result),
        f"分析方式：{'AI 先识别热度板块，再生成观察池' if ai_used else '规则兜底识别板块'}",
        "",
        "一、重点热搜",
    ]
    if hotspots:
        for index, item in enumerate(hotspots[:6], 1):
            rank = item.get("rank") or "-"
            hot = f"｜{item.get('hot_value')}" if item.get("hot_value") else ""
            lines.append(f"{index}. [{item.get('platform')} #{rank}] {item.get('title')}{hot}")
    else:
        lines.append("暂无最近 2 小时热搜数据。")

    lines.append("")
    lines.append("二、热点板块雷达")
    lines.extend(_format_sector_radar(related))

    lines.append("")
    lines.append("三、股票观察池（仅作板块下补充）")
    if items:
        for index, item in enumerate(items[:6], 1):
            reasons = "；".join((item.get("reasons") or [])[:2]) or "基于主题/行业弱关联"
            relation = item.get("relationType") or "主题关联"
            ai_reason = store.text(item.get("aiReason"))
            lines.append(
                f"{index}. {item.get('name')}({item.get('code')})｜{item.get('theme')}｜{relation}｜{_format_quote(item)}｜匹配度 {item.get('confidence', 0)}%｜{reasons}"
            )
            if ai_reason:
                lines.append(f"   AI依据：{ai_reason}")
    else:
        lines.append("暂未匹配到明确候选标的。")

    lines.append("")
    lines.append("合规提示：以上仅为热点与板块/行业的弱关联识别，股票为观察池补充，不代表因果关系、买卖建议或收益承诺。")
    return {
        "text": "\n".join(lines),
        "hotspotCount": len(hotspots),
        "stockCount": len(items),
        "sectorCount": len(sectors),
        "themeCount": len(themes),
        "refresh": refresh_result or {},
    }


def _format_refresh_line(refresh_result: dict[str, Any] | None) -> str:
    result = store.safe_object(refresh_result)
    if not result:
        return "刷新状态：未触发热搜刷新"
    if result.get("ok"):
        success = len(result.get("successPlatforms") or [])
        failed = len(result.get("failedPlatforms") or [])
        return f"刷新状态：已先刷新热搜，获取 {result.get('totalItems') or 0} 条，成功 {success} 个平台{f'，失败 {failed} 个平台' if failed else ''}"
    return f"刷新状态：热搜刷新失败，已使用现有缓存继续推送（{result.get('error') or '未知错误'}）"


def send_text(webhook_url: str, text: str) -> dict[str, Any]:
    if not webhook_url:
        raise RuntimeError("飞书 webhook 未配置")
    response = requests.post(
        webhook_url,
        json={"msg_type": "text", "content": {"text": text}},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    code = payload.get("code", payload.get("StatusCode"))
    if code not in (None, 0):
        raise RuntimeError(payload.get("msg") or payload.get("StatusMessage") or f"飞书返回错误：{code}")
    return payload


def push_now(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    refresh_result = refresh_hotspots_before_push()
    message = build_message(cfg, refresh_result)
    result = send_text(store.text(cfg.get("webhookUrl")), message["text"])
    refresh_label = "已刷新热搜" if refresh_result.get("ok") else "刷新失败使用缓存"
    next_settings = {
        **cfg,
        "lastPushedAt": _now_iso(),
        "lastStatus": f"成功推送：{message.get('sectorCount', 0)} 个热点板块，{message['stockCount']} 个观察标的，{refresh_label}",
    }
    store.set_kv(SETTINGS_KEY, next_settings)
    return {"ok": True, "message": next_settings["lastStatus"], "feishu": result, "payload": message}


def due_to_push(settings: dict[str, Any] | None = None) -> bool:
    cfg = settings or get_settings()
    if not cfg.get("enabled") or not cfg.get("webhookUrl"):
        return False
    last = store.text(cfg.get("lastPushedAt"))
    if not last:
        return True
    try:
        parsed = datetime.fromisoformat(last.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return True
    return datetime.now(timezone.utc) - parsed >= timedelta(minutes=int(cfg.get("intervalMinutes") or 120))
