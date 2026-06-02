from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import db
import store
from services import hotspot_fetcher, hotspot_stock_matcher


SETTINGS_KEY = "feishu-hotspot-push-settings"
logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_settings() -> dict[str, Any]:
    saved = store.safe_object(store.get_kv(SETTINGS_KEY, {}))
    return {
        "enabled": bool(saved.get("enabled", False)),
        "webhookUrl": store.text(saved.get("webhookUrl")),
        "intervalMinutes": max(15, store.to_int(saved.get("intervalMinutes"), 120) or 120),
        "pushRelatedStocks": saved.get("pushRelatedStocks", True) is not False,
        "notifyRegistrations": saved.get("notifyRegistrations", True) is not False,
        "lastPushedAt": store.text(saved.get("lastPushedAt")),
        "lastStatus": store.text(saved.get("lastStatus")),
        "lastRegistrationNotifiedAt": store.text(saved.get("lastRegistrationNotifiedAt")),
        "lastRegistrationStatus": store.text(saved.get("lastRegistrationStatus")),
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
        "notifyRegistrations": incoming.get("notifyRegistrations", current.get("notifyRegistrations", True)) is not False,
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


def _short_text(value: Any, limit: int = 56) -> str:
    text = " ".join(store.text(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


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


def _sector_observation_text(sector: dict[str, Any], include_stocks: bool) -> str:
    if not include_stocks:
        return "观察池：已关闭"
    stocks = sector.get("stocks") if isinstance(sector.get("stocks"), list) else []
    names = []
    for item in stocks[:3]:
        name = store.text(item.get("name"))
        code = store.text(item.get("code"))
        if not name:
            continue
        code_part = f" {code}" if code else ""
        names.append(f"{name}{code_part} {_format_quote(item)}")
    return "观察池：" + ("、".join(names) if names else "暂无明确标的")


def _sector_evidence_text(sector: dict[str, Any]) -> str:
    evidence = sector.get("evidence") if isinstance(sector.get("evidence"), list) else []
    if not evidence:
        reason = store.text(sector.get("reason"))
        return f"依据：{_short_text(reason, 64)}" if reason else "依据：暂无明确财经证据"
    first_hit = store.safe_object(evidence[0])
    platform = store.text(first_hit.get("platform") or "source")
    rank = first_hit.get("rank") or "-"
    title = _short_text(first_hit.get("title"), 62)
    return f"依据：[{platform} #{rank}] {title}"


def _format_sector_digest(related: dict[str, Any], include_stocks: bool = True) -> list[str]:
    sectors = related.get("sectors") if isinstance(related.get("sectors"), list) else []
    if not sectors:
        return _format_ai_insights(related)
    lines = []
    for index, sector in enumerate(sectors[:3], 1):
        theme = store.text(sector.get("theme") or "未命名板块")
        score = store.to_int(sector.get("heatScore"), 0) or 0
        reason = store.text(sector.get("reason"))
        keywords = "、".join(store.text(word) for word in (sector.get("keywords") or [])[:5] if store.text(word))
        lines.append(f"{index}. {theme}｜{score}分")
        focus = reason or (f"关键词：{keywords}" if keywords else "")
        if focus:
            lines.append(f"   看点：{_short_text(focus, 62)}")
        lines.append(f"   {_sector_evidence_text(sector)}")
        lines.append(f"   {_sector_observation_text(sector, include_stocks)}")
    return lines


def build_message(settings: dict[str, Any] | None = None, refresh_result: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    include_stocks = cfg.get("pushRelatedStocks", True) is not False
    related = hotspot_stock_matcher.match_related_stocks({"limit": 12, "quoteLimit": 4 if include_stocks else 0})
    items = related.get("items") if isinstance(related.get("items"), list) else []
    sectors = related.get("sectors") or []
    themes = related.get("themes") or []
    ai_used = bool(related.get("aiUsed"))
    source_count = related.get("sourceHotspotCount") or 0
    lines = [
        "FinVue 热点板块雷达",
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}｜{_format_refresh_line(refresh_result)}",
        f"分析：{'AI识别板块' if ai_used else '规则兜底'}｜依据 {source_count or '若干'} 条财经/总览消息",
        "",
        f"Top 3 热点板块{'（含观察池）' if include_stocks else ''}",
    ]
    lines.extend(_format_sector_digest(related, include_stocks))
    lines.extend([
        "",
        "合规提示：以上为热点与板块/行业的弱关联观察，不构成因果判断、买卖建议或收益承诺。",
    ])

    return {
        "text": "\n".join(lines),
        "hotspotCount": int(source_count or 0),
        "stockCount": len(items) if include_stocks else 0,
        "sectorCount": len(sectors),
        "themeCount": len(themes),
        "refresh": refresh_result or {},
    }


def _format_refresh_line(refresh_result: dict[str, Any] | None) -> str:
    result = store.safe_object(refresh_result)
    if not result:
        return "未触发刷新"
    if result.get("ok"):
        success = len(result.get("successPlatforms") or [])
        stale = len(result.get("stalePlatforms") or [])
        failed = len(result.get("failedPlatforms") or [])
        suffix_parts = []
        if stale:
            suffix_parts.append(f"{stale} 平台旧缓存未写入")
        if failed:
            suffix_parts.append(f"{failed} 平台失败")
        suffix = "，" + "，".join(suffix_parts) if suffix_parts else ""
        fetched = result.get("fetchedItems") or result.get("totalItems") or 0
        saved = result.get("totalItems") or 0
        return f"有效 {saved} 条 / 抓取 {fetched} 条 / {success} 平台{suffix}"
    return f"刷新失败，使用缓存（{_short_text(result.get('error') or '未知错误', 28)}）"


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


def build_registration_message(user: dict[str, Any], request_ip: str = "") -> str:
    username = store.text(user.get("username")) or "未知用户"
    role = store.text(user.get("role")) or "user"
    permissions = store.safe_object(user.get("permissions"))
    enabled_permissions = [key for key, value in permissions.items() if value is True]
    permission_text = "、".join(enabled_permissions[:6]) if enabled_permissions else "默认用户权限"
    return "\n".join([
        "FinVue 新用户注册",
        f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"账号：{username}",
        f"角色：{role}",
        f"来源 IP：{store.text(request_ip) or '未知'}",
        f"初始权限：{permission_text}",
    ])


def notify_registration(user: dict[str, Any], request_ip: str = "") -> dict[str, Any]:
    cfg = get_settings()
    webhook_url = store.text(cfg.get("webhookUrl"))
    if not webhook_url:
        return {"ok": False, "skipped": True, "reason": "飞书 webhook 未配置"}
    if cfg.get("notifyRegistrations") is False:
        return {"ok": False, "skipped": True, "reason": "注册通知未启用"}
    result = send_text(webhook_url, build_registration_message(user, request_ip))
    next_settings = {
        **cfg,
        "lastRegistrationNotifiedAt": _now_iso(),
        "lastRegistrationStatus": f"已通知新用户注册：{store.text(user.get('username')) or '未知用户'}",
    }
    store.set_kv(SETTINGS_KEY, next_settings)
    return {"ok": True, "feishu": result, "message": next_settings["lastRegistrationStatus"]}


def notify_registration_safe(user: dict[str, Any], request_ip: str = "") -> dict[str, Any]:
    try:
        return notify_registration(user, request_ip)
    except Exception as exc:
        logger.exception("[feishu] registration notification failed username=%s", user.get("username"))
        try:
            cfg = get_settings()
            store.set_kv(SETTINGS_KEY, {
                **cfg,
                "lastRegistrationNotifiedAt": _now_iso(),
                "lastRegistrationStatus": f"注册通知失败：{_short_text(str(exc), 40)}",
            })
        except Exception:
            logger.exception("[feishu] failed to persist registration notification error")
        return {"ok": False, "error": str(exc)}


def push_now(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    refresh_result = refresh_hotspots_before_push()
    message = build_message(cfg, refresh_result)
    result = send_text(store.text(cfg.get("webhookUrl")), message["text"])
    if refresh_result.get("ok"):
        stale_count = len(refresh_result.get("stalePlatforms") or [])
        refresh_label = f"已刷新热搜{f'，{stale_count} 个平台旧缓存未写入' if stale_count else ''}"
    else:
        refresh_label = "刷新失败使用缓存"
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
