"""热搜抓取服务 - 从热点 API 获取多平台热搜数据"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

import config
import db


# 热点 API 基础地址（可通过环境变量 HOTSPOT_API_URL 配置）
HOTSPOT_API_BASE = config.HOTSPOT_API_URL

# 平台 ID 映射（newsnow 使用的 ID）
PLATFORM_ID_MAP = {
    "weibo": "weibo",
    "zhihu": "zhihu",
    "baidu": "baidu",
    "douyin": "douyin",
    "bilibili": "bilibili",
    "toutiao": "toutiao",
    "cls": "cls",
    "wallstreetcn": "wallstreetcn-hot",
    "ifeng": "ifeng",
    "pengpai": "pengpai",
    "tieba": "tieba",
}

# 平台分类
PLATFORM_CATEGORY_MAP = {
    "weibo": "social",
    "zhihu": "social",
    "baidu": "search",
    "douyin": "video",
    "bilibili": "video",
    "toutiao": "news",
    "cls": "finance",
    "wallstreetcn": "finance",
    "ifeng": "news",
    "pengpai": "news",
    "tieba": "social",
}


def _id(prefix: str = "hotspot") -> str:
    """生成唯一 ID"""
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _json(value: Any) -> str:
    """序列化 JSON"""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _hash_title_platform(title: str, platform: str) -> str:
    """生成热搜条目的唯一哈希 ID"""
    normalized = f"{platform}:{title.strip().lower()}"
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]


def _extract_keywords(title: str) -> list[str]:
    """从标题中提取关键词"""
    # 简单提取：去除标点，按空格/标点分割，过滤短词
    title = re.sub(r"[【】《》\[\]（）()「」『』]", " ", title)
    words = re.split(r"[,，、；;：:·\s]+", title)
    keywords = []
    for w in words:
        w = w.strip()
        if len(w) >= 2 and len(w) <= 20 and not w.isdigit():
            keywords.append(w)
    return keywords[:5]


def fetch_platform_hotspots(platform: str) -> dict:
    """抓取单个平台的热搜数据（使用 TrendRadar 的 API）"""
    import requests
    import os

    newnow_id = PLATFORM_ID_MAP.get(platform, platform)
    # TrendRadar API 格式: /api/s?id={id}&latest
    url = f"{HOTSPOT_API_BASE}?id={newnow_id}&latest"

    # 正确处理代理配置：只有环境变量明确设置了非空代理才使用
    # HOTSPOT_NO_PROXY=1 可以完全禁用代理
    proxies = None
    if os.environ.get("HOTSPOT_NO_PROXY") != "1":
        http_proxy = os.environ.get("http_proxy") or os.environ.get("HTTP_PROXY")
        if http_proxy and http_proxy.strip() and "://" in http_proxy:
            proxies = {"http": http_proxy.strip(), "https": http_proxy.strip()}

    # 设置请求头，模拟正常浏览器
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    # 重试策略：先尝试带代理（如果有），失败再尝试无代理
    attempts = []
    if proxies:
        attempts.append(("proxy", proxies))
    attempts.append(("direct", None))

    last_error = None
    for attempt_name, attempt_proxies in attempts:
        try:
            resp = requests.get(url, proxies=attempt_proxies, headers=headers, timeout=30)
            if resp.status_code != 200:
                last_error = f"HTTP {resp.status_code}"
                continue

            data = resp.json()

            # TrendRadar API 返回格式: {"status": "cache", "id": "weibo", "items": [{id, title, url, mobileUrl, extra}]}
            # 或者旧格式: {"code": 200, "data": [...]}
            items = []

            if isinstance(data, dict):
                # 新 API 格式 - items 数组
                if "items" in data and isinstance(data["items"], list):
                    for idx, news in enumerate(data["items"]):
                        title = news.get("title") or ""
                        if not title:
                            continue
                        items.append({
                            "id": _hash_title_platform(title, platform),
                            "title": title.strip(),
                            "url": news.get("url") or news.get("mobileUrl") or "",
                            "rank": idx + 1,
                            "hotValue": "",
                            "sourceId": news.get("id") or "",
                            "sourceName": "",
                        })
                # 旧 API 格式 - code + data
                elif data.get("code") == 200 and isinstance(data.get("data"), list):
                    for idx, news in enumerate(data["data"]):
                        title = news.get("title") or ""
                        if not title:
                            continue
                        items.append({
                            "id": _hash_title_platform(title, platform),
                            "title": title.strip(),
                            "url": news.get("url") or news.get("sourceUrl") or "",
                            "rank": idx + 1,
                            "hotValue": news.get("hotValue") or news.get("hot") or str(news.get("score") or ""),
                            "sourceId": news.get("sourceId") or news.get("id") or "",
                            "sourceName": news.get("sourceName") or "",
                        })
                # 嵌套格式 - {id_value: {title: {ranks, url, mobileUrl}}}
                elif newnow_id in data and isinstance(data[newnow_id], dict):
                    platform_data = data[newnow_id]
                    for idx, (title, info) in enumerate(platform_data.items()):
                        if not title or not isinstance(info, dict):
                            continue
                        ranks = info.get("ranks") or []
                        current_rank = ranks[0] if ranks else (idx + 1)
                        items.append({
                            "id": _hash_title_platform(title, platform),
                            "title": title.strip(),
                            "url": info.get("url") or info.get("mobileUrl") or "",
                            "rank": current_rank,
                            "hotValue": "",
                            "sourceId": "",
                            "sourceName": "",
                        })
                    items.sort(key=lambda x: x["rank"])
                else:
                    last_error = "API 返回数据格式错误或无数据"
                    continue
            elif isinstance(data, list):
                # 直接是数组格式
                for idx, news in enumerate(data):
                    title = news.get("title") or ""
                    if not title:
                        continue
                    items.append({
                        "id": _hash_title_platform(title, platform),
                        "title": title.strip(),
                        "url": news.get("url") or news.get("mobileUrl") or "",
                        "rank": idx + 1,
                        "hotValue": news.get("hotValue") or "",
                        "sourceId": news.get("id") or "",
                        "sourceName": "",
                    })
            else:
                last_error = "API 返回数据格式错误"
                continue

            return {"ok": True, "platform": platform, "items": items, "count": len(items)}

        except Exception as e:
            last_error = str(e)
            continue

    return {"ok": False, "platform": platform, "error": last_error or "连接失败"}


def fetch_all_platforms(platforms: list[str] | None = None) -> dict:
    """抓取所有启用平台的热搜数据（使用线程池并发）"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 检查 API 是否启用
    if not config.HOTSPOT_API_ENABLED:
        return {
            "ok": False,
            "error": "热点 API 已禁用。请在环境变量中设置 HOTSPOT_API_ENABLED=true 启用，或手动输入热点关键词。",
            "totalItems": 0,
            "successPlatforms": [],
            "failedPlatforms": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    if not platforms:
        platforms = list(PLATFORM_ID_MAP.keys())

    results = []
    with ThreadPoolExecutor(max_workers=min(len(platforms), 10)) as executor:
        futures = {executor.submit(fetch_platform_hotspots, p): p for p in platforms}
        for future in as_completed(futures):
            results.append(future.result())

    total_items = 0
    success_platforms = []
    failed_platforms = []

    for result in results:
        if result.get("ok"):
            success_platforms.append(result["platform"])
            total_items += result.get("count", 0)
            # 保存到数据库
            save_hotspot_items(result["platform"], result.get("items", []))
        else:
            failed_platforms.append({
                "platform": result.get("platform"),
                "error": result.get("error")
            })

    return {
        "ok": True,
        "totalItems": total_items,
        "successPlatforms": success_platforms,
        "failedPlatforms": failed_platforms,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def save_hotspot_items(platform: str, items: list[dict]) -> int:
    """保存热搜数据到数据库"""
    if not items:
        return 0

    now = datetime.now(timezone.utc)
    saved_count = 0

    for item in items:
        item_id = item.get("id") or _hash_title_platform(item.get("title", ""), platform)
        title = item.get("title", "").strip()
        if not title:
            continue

        url = item.get("url", "")
        rank = int(item.get("rank", 0))
        hot_value = str(item.get("hotValue", ""))
        keywords = _extract_keywords(title)

        # 检查是否已存在
        existing = db.fetch_one(
            "SELECT id, appearance_count FROM finvue_hotspot_items WHERE id = %s",
            (item_id,)
        )

        if existing:
            # 更新已有条目
            appearance_count = existing.get("appearance_count", 1) + 1
            db.execute(
                """
                UPDATE finvue_hotspot_items
                SET `rank` = %s, hot_value = %s, last_seen_at = CURRENT_TIMESTAMP,
                    appearance_count = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (rank, hot_value, appearance_count, item_id)
            )

            # 添加快照
            db.execute(
                """
                INSERT INTO finvue_hotspot_snapshots (id, item_id, platform, title, `rank`, hot_value, snapshot_time)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE `rank` = VALUES(`rank`), hot_value = VALUES(hot_value)
                """,
                (f"{item_id}-{now.strftime('%Y%m%d%H%M')}", item_id, platform, title, rank, hot_value)
            )
        else:
            # 新增条目
            db.execute(
                """
                INSERT INTO finvue_hotspot_items
                (id, platform, title, url, `rank`, hot_value, keywords, first_seen_at, last_seen_at, appearance_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)
                """,
                (item_id, platform, title, url, rank, hot_value, _json(keywords))
            )

            # 添加初始快照
            db.execute(
                """
                INSERT INTO finvue_hotspot_snapshots (id, item_id, platform, title, `rank`, hot_value, snapshot_time)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (f"{item_id}-{now.strftime('%Y%m%d%H%M')}", item_id, platform, title, rank, hot_value)
            )

        saved_count += 1

    return saved_count


def sync_fetch_all_platforms(platforms: list[str] | None = None) -> dict:
    """同步版本的抓取函数（用于 worker 调用）"""
    import asyncio
    return asyncio.run(fetch_all_platforms(platforms))


def cleanup_old_data(retention_days: int = 30) -> dict:
    """清理超过保留天数的历史数据"""
    from datetime import timedelta

    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")

    # 删除旧的热搜条目（快照会通过外键级联删除）
    result = db.execute(
        "DELETE FROM finvue_hotspot_items WHERE last_seen_at < %s",
        (cutoff_str,)
    )

    return {"ok": True, "deleted": result or 0, "cutoffDate": cutoff_str}