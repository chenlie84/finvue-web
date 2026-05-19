"""热搜抓取服务 - 从 newsnow API 获取多平台热搜数据"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

import config
import db


# newsnow API 基础地址
NEWSNOW_API_BASE = "https://api.v1.newnow.today/api/v1/buss/news/getNewsList"

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


async def fetch_platform_hotspots(platform: str) -> dict:
    """抓取单个平台的热搜数据"""
    import aiohttp

    newnow_id = PLATFORM_ID_MAP.get(platform, platform)
    url = f"{NEWSNOW_API_BASE}?type={newnow_id}"

    # 使用项目配置的代理（内部服务器访问外网需要走代理）
    proxy = None
    if config.HTTP_PROXY:
        proxy = config.HTTP_PROXY

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            async with session.get(url, proxy=proxy) as resp:
                if resp.status != 200:
                    return {"ok": False, "platform": platform, "error": f"HTTP {resp.status}"}

                data = await resp.json()
                if not data or data.get("code") != 200:
                    return {"ok": False, "platform": platform, "error": data.get("msg") or "API 返回错误"}

                news_list = data.get("data") or []
                items = []

                for idx, news in enumerate(news_list):
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

                return {"ok": True, "platform": platform, "items": items, "count": len(items)}

    except Exception as e:
        return {"ok": False, "platform": platform, "error": str(e)}


async def fetch_all_platforms(platforms: list[str] | None = None) -> dict:
    """抓取所有启用平台的热搜数据"""
    import asyncio

    if not platforms:
        platforms = list(PLATFORM_ID_MAP.keys())

    tasks = [fetch_platform_hotspots(p) for p in platforms]
    results = await asyncio.gather(*tasks)

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