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


def build_message(settings: dict[str, Any] | None = None, refresh_result: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    hotspots = _recent_hotspots()
    related = (
        hotspot_stock_matcher.match_related_stocks({"limit": 12, "quoteLimit": 8})
        if cfg.get("pushRelatedStocks", True)
        else {"items": [], "themes": []}
    )
    items = related.get("items") or []
    themes = related.get("themes") or []
    lines = [
        "FinVue 热点关联标的雷达",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}",
        _format_refresh_line(refresh_result),
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
    lines.append("二、关联主题")
    if themes:
        lines.append("、".join(str(item.get("theme") or "") for item in themes[:6] if item.get("theme")))
    else:
        lines.append("暂未识别出明确主题。")

    lines.append("")
    lines.append("三、关联标的候选")
    if items:
        for index, item in enumerate(items[:8], 1):
            reasons = "；".join((item.get("reasons") or [])[:2]) or "基于主题/行业弱关联"
            relation = item.get("relationType") or "主题关联"
            lines.append(
                f"{index}. {item.get('name')}({item.get('code')})｜{item.get('theme')}｜{relation}｜{_format_quote(item)}｜匹配度 {item.get('confidence', 0)}%｜{reasons}"
            )
    else:
        lines.append("暂未匹配到明确候选标的。")

    lines.append("")
    lines.append("合规提示：以上仅为热点与行业/标的的弱关联召回，不代表因果关系、买卖建议或收益承诺。")
    return {
        "text": "\n".join(lines),
        "hotspotCount": len(hotspots),
        "stockCount": len(items),
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
        "lastStatus": f"成功推送：{message['stockCount']} 个候选标的，{refresh_label}",
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
