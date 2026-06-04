from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

import ai_router
import db
import store
from services import hotspot_fetcher, hotspot_stock_matcher


SETTINGS_KEY = "feishu-hotspot-push-settings"
logger = logging.getLogger(__name__)
LOCAL_TZ = timezone(timedelta(hours=8), "Asia/Shanghai")
DEFAULT_DAILY_PUSH_TIME = "09:00"
PLATFORM_NAMES = {
    "weibo": "微博",
    "zhihu": "知乎",
    "baidu": "百度",
    "douyin": "抖音",
    "bilibili": "B站",
    "toutiao": "头条",
    "cls": "财联社",
    "wallstreetcn": "华尔街见闻",
    "ifeng": "凤凰网",
    "pengpai": "澎湃新闻",
    "tieba": "贴吧",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_daily_push_time(value: Any) -> str:
    text = store.text(value) or DEFAULT_DAILY_PUSH_TIME
    match = re.match(r"^(\d{1,2}):(\d{2})$", text)
    if not match:
        return DEFAULT_DAILY_PUSH_TIME
    hour = max(0, min(23, int(match.group(1))))
    minute = max(0, min(59, int(match.group(2))))
    return f"{hour:02d}:{minute:02d}"


def get_settings() -> dict[str, Any]:
    saved = store.safe_object(store.get_kv(SETTINGS_KEY, {}))
    return {
        "enabled": bool(saved.get("enabled", False)),
        "webhookUrl": store.text(saved.get("webhookUrl")),
        "intervalMinutes": max(15, store.to_int(saved.get("intervalMinutes"), 120) or 120),
        "dailyPushTime": _normalize_daily_push_time(saved.get("dailyPushTime")),
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
        "dailyPushTime": _normalize_daily_push_time(incoming.get("dailyPushTime", current.get("dailyPushTime"))),
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


def _clean_markdown_inline(value: Any) -> str:
    text = store.text(value)
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return " ".join(text.strip(" -•\t").split())


def _recent_summary_hotspots(top_per_platform: int = 8) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    rows = db.fetch_all(
        """
        SELECT platform, title, url, `rank`, hot_value, last_seen_at
        FROM finvue_hotspot_items
        WHERE last_seen_at >= DATE_SUB(NOW(), INTERVAL 2 HOUR)
        ORDER BY platform ASC, `rank` ASC
        LIMIT 240
        """
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        platform = store.text(row.get("platform"))
        title = store.text(row.get("title"))
        if not platform or not title:
            continue
        items = grouped.setdefault(platform, [])
        if len(items) >= top_per_platform:
            continue
        items.append({
            "platform": platform,
            "title": title,
            "rank": row.get("rank") or 0,
            "hotValue": store.text(row.get("hot_value")),
            "url": store.text(row.get("url")),
        })
    items = [item for platform_items in grouped.values() for item in platform_items if item.get("title")]
    return items, grouped


def _hotspot_lines_for_summary(items: list[dict[str, Any]], top_per_platform: int) -> list[str]:
    lines = []
    for item in items:
        platform_label = PLATFORM_NAMES.get(store.text(item.get("platform")), store.text(item.get("platform")))
        hot = f"｜热度 {item['hotValue']}" if item.get("hotValue") else ""
        lines.append(f"- [{platform_label} #{item.get('rank') or '-'}] {item.get('title')}{hot}")
    return lines


def _generate_push_summary() -> dict[str, Any]:
    top_per_platform = 8
    items, grouped = _recent_summary_hotspots(top_per_platform)
    if not items:
        return {"analysis": "", "itemCount": 0, "platforms": [], "error": "暂无可分析的热搜数据"}

    system_prompt = """你是财经直播内容主编和投顾合规助手。你需要从全网热搜中筛出真正重要、适合投顾团队关注的新闻，并转化为直播选题。
要求：
1. 优先关注财经、宏观政策、产业链、上市公司、科技、消费、监管、地缘风险等与投资相关的话题。
2. 对纯娱乐、低价值八卦、重复话题要降权或忽略。
3. 不编造具体股票买卖建议，不承诺收益，不输出荐股结论。
4. 输出必须简洁，适合飞书推送和后台顶部展示。"""

    user_prompt = f"""下面是最近一轮热搜数据，每个平台取前 {top_per_platform} 条：

{chr(10).join(_hotspot_lines_for_summary(items, top_per_platform))}

请输出 Markdown，总长度控制在 800 字以内，结构如下：

# 今日热搜总览

## 最值得关注的 5 条
用编号列表输出，每条包含：事件、为什么重要、可能影响的行业/方向。

## 直播可用选题
给出 3-4 个适合财经直播展开的话题角度。

## 风险与合规提醒
列出 2-3 条讨论时需要避开的表达边界。

## 可忽略噪音
用一句话概括本轮哪些类型热搜价值较低。"""

    try:
        ai_result = ai_router.generate({"systemPrompt": system_prompt, "userPrompt": user_prompt}, username="")
        analysis = store.text(ai_result.get("markdown"))
        return {
            "analysis": analysis,
            "itemCount": len(items),
            "platforms": sorted(grouped.keys()),
            "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "aiMeta": ai_result.get("aiMeta"),
        }
    except Exception as exc:
        logger.exception("[feishu] failed to generate hotspot summary for push")
        return {
            "analysis": "",
            "itemCount": len(items),
            "platforms": sorted(grouped.keys()),
            "error": str(exc),
        }


def _extract_markdown_section(markdown: str, heading_keywords: list[str]) -> str:
    if not markdown:
        return ""
    pattern = re.compile(r"^##\s*(.+?)\s*$", re.M)
    matches = list(pattern.finditer(markdown))
    for index, match in enumerate(matches):
        title = match.group(1)
        if not any(keyword in title for keyword in heading_keywords):
            continue
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        return markdown[start:end].strip()
    return ""


def _extract_numbered_items(section: str, limit: int) -> list[str]:
    if not section:
        return []
    items: list[str] = []
    current: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if re.match(r"^(\d+[\.\、)]|[-*•])\s+", line):
            if current:
                items.append(_clean_markdown_inline(" ".join(current)))
            current = [re.sub(r"^(\d+[\.\、)]|[-*•])\s+", "", line)]
        elif current:
            current.append(line)
    if current:
        items.append(_clean_markdown_inline(" ".join(current)))
    return [item for item in items if item][:limit]


def _fallback_focus_items(limit: int = 5) -> list[str]:
    preferred = {"cls", "wallstreetcn", "toutiao", "baidu"}
    items, _ = _recent_summary_hotspots(10)
    ranked = sorted(
        items,
        key=lambda item: (0 if item.get("platform") in preferred else 1, int(item.get("rank") or 999)),
    )
    lines = []
    for item in ranked[:limit]:
        platform = PLATFORM_NAMES.get(store.text(item.get("platform")), store.text(item.get("platform")))
        lines.append(f"[{platform} #{item.get('rank') or '-'}] {item.get('title')}")
    return lines


def _summary_focus_items(summary_text: str, limit: int = 5) -> list[str]:
    section = _extract_markdown_section(summary_text, ["最值得关注", "值得盯", "重点新闻"])
    return _extract_numbered_items(section, limit) or _fallback_focus_items(limit)


def _summary_live_topics(summary_text: str, limit: int = 3) -> list[str]:
    section = _extract_markdown_section(summary_text, ["直播可用", "直播选题", "可用选题"])
    return _extract_numbered_items(section, limit)


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


def _format_focus_digest(summary_text: str, limit: int = 5) -> list[str]:
    return [f"{index}. {_short_text(item, 88)}" for index, item in enumerate(_summary_focus_items(summary_text, limit), 1)]


def _format_live_topic_digest(summary_text: str, limit: int = 3) -> list[str]:
    topics = _summary_live_topics(summary_text, limit)
    return [f"{index}. {_short_text(item, 82)}" for index, item in enumerate(topics, 1)]


def _card_text(content: str, tag: str = "lark_md") -> dict[str, Any]:
    return {"tag": tag, "content": content}


def _card_div(content: str, tag: str = "lark_md") -> dict[str, Any]:
    return {"tag": "div", "text": _card_text(content, tag)}


def _format_sector_card_block(related: dict[str, Any], include_stocks: bool = True) -> str:
    sectors = related.get("sectors") if isinstance(related.get("sectors"), list) else []
    if not sectors:
        return "\n".join(_format_ai_insights(related)[:3])
    blocks = []
    for index, sector in enumerate(sectors[:3], 1):
        theme = store.text(sector.get("theme") or "未命名板块")
        score = store.to_int(sector.get("heatScore"), 0) or 0
        keywords = "、".join(store.text(word) for word in (sector.get("keywords") or [])[:5] if store.text(word))
        evidence = _sector_evidence_text(sector).replace("依据：", "")
        observation = _sector_observation_text(sector, include_stocks).replace("观察池：", "")
        lines = [
            f"**{index}. {theme}｜{score}分**",
            f"触发：{_short_text(evidence, 86)}",
        ]
        if keywords:
            lines.append(f"关键词：{keywords}")
        if include_stocks:
            lines.append(f"观察池：{_short_text(observation, 96)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _build_feishu_card(
    *,
    summary_text: str,
    related: dict[str, Any],
    include_stocks: bool,
    refresh_result: dict[str, Any] | None,
    ai_used: bool,
    source_count: int,
) -> dict[str, Any]:
    focus_lines = _format_focus_digest(summary_text)
    topic_lines = _format_live_topic_digest(summary_text)
    generated_at = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d %H:%M")
    method = "AI总览 + AI板块识别" if ai_used else "AI总览 + 规则兜底"
    if not summary_text:
        method = "规则兜底"
    elements: list[dict[str, Any]] = [
        _card_div(f"**{generated_at}**｜{_format_refresh_line(refresh_result)}\n分析：{method}｜依据 {source_count or '若干'} 条财经/总览消息"),
        {"tag": "hr"},
        _card_div("**本轮最值得盯的 5 条**\n" + ("\n".join(focus_lines) if focus_lines else "暂无可用总览，已使用板块雷达兜底。")),
        {"tag": "hr"},
        _card_div("**Top 3 热点板块" + ("（含观察池）" if include_stocks else "") + "**\n" + _format_sector_card_block(related, include_stocks)),
    ]
    if topic_lines:
        elements.extend([
            {"tag": "hr"},
            _card_div("**直播可用选题**\n" + "\n".join(topic_lines)),
        ])
    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "template": "blue",
            "title": {"tag": "plain_text", "content": "FinVue 热点雷达"},
        },
        "elements": elements,
    }


def build_message(settings: dict[str, Any] | None = None, refresh_result: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = settings or get_settings()
    include_stocks = cfg.get("pushRelatedStocks", True) is not False
    summary = _generate_push_summary()
    summary_text = store.text(summary.get("analysis"))
    related = hotspot_stock_matcher.match_related_stocks({
        "summary": summary_text,
        "limit": 12,
        "quoteLimit": 4 if include_stocks else 0,
        "useAi": True,
    })
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
        "一、本轮最值得盯的 5 条",
    ]
    lines.extend(_format_focus_digest(summary_text))
    lines.extend([
        "",
        f"Top 3 热点板块{'（含观察池）' if include_stocks else ''}",
    ])
    lines.extend(_format_sector_digest(related, include_stocks))
    topic_lines = _format_live_topic_digest(summary_text)
    if topic_lines:
        lines.extend(["", "三、直播可用选题", *topic_lines])

    return {
        "text": "\n".join(lines),
        "card": _build_feishu_card(
            summary_text=summary_text,
            related=related,
            include_stocks=include_stocks,
            refresh_result=refresh_result,
            ai_used=ai_used,
            source_count=int(source_count or 0),
        ),
        "summary": summary,
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


def _send_payload(webhook_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not webhook_url:
        raise RuntimeError("飞书 webhook 未配置")
    response = requests.post(
        webhook_url,
        json=payload,
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    code = payload.get("code", payload.get("StatusCode"))
    if code not in (None, 0):
        raise RuntimeError(payload.get("msg") or payload.get("StatusMessage") or f"飞书返回错误：{code}")
    return payload


def send_text(webhook_url: str, text: str) -> dict[str, Any]:
    return _send_payload(webhook_url, {"msg_type": "text", "content": {"text": text}})


def send_interactive_card(webhook_url: str, card: dict[str, Any]) -> dict[str, Any]:
    return _send_payload(webhook_url, {"msg_type": "interactive", "card": card})


def send_message(webhook_url: str, message: dict[str, Any]) -> dict[str, Any]:
    card = store.safe_object(message.get("card"))
    if card:
        try:
            return send_interactive_card(webhook_url, card)
        except Exception:
            logger.exception("[feishu] interactive card failed, fallback to text")
    return send_text(webhook_url, store.text(message.get("text")))


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
    result = send_message(store.text(cfg.get("webhookUrl")), message)
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
    local_now = datetime.now(LOCAL_TZ)
    hour_text, minute_text = _normalize_daily_push_time(cfg.get("dailyPushTime")).split(":")
    scheduled = local_now.replace(hour=int(hour_text), minute=int(minute_text), second=0, microsecond=0)
    if local_now < scheduled:
        return False
    last = store.text(cfg.get("lastPushedAt"))
    if not last:
        return True
    try:
        parsed = datetime.fromisoformat(last.replace("Z", "+00:00")).astimezone(LOCAL_TZ)
    except Exception:
        return True
    return parsed.date() < local_now.date()
