"""热点追踪 API 模块 - 独立解耦设计"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import db
import security
import ai_router


router = APIRouter()


# ============================================
# 辅助函数
# ============================================

def _id(prefix: str = "hotspot") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def parse_json(value: Any, fallback: Any = None) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return fallback


def text(value: Any) -> str:
    return str(value or "").strip()


def iso(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def paginate(page: int = 1, page_size: int = 20) -> tuple[int, int]:
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    return page, page_size


# ============================================
# 平台信息
# ============================================

@router.get("/api/hotspot/platforms")
def get_platforms(_: dict = Depends(security.require_permission("hotspot"))) -> dict:
    """获取所有可用平台列表"""
    rows = db.fetch_all(
        "SELECT id, name, category, icon, enabled, priority FROM finvue_hotspot_platforms ORDER BY priority ASC"
    )
    platforms = [
        {
            "id": row["id"],
            "name": row["name"],
            "category": row.get("category") or "news",
            "icon": row.get("icon") or "🔥",
            "enabled": bool(row.get("enabled")),
            "priority": row.get("priority") or 100,
        }
        for row in rows
    ]
    return {"ok": True, "platforms": platforms}


# ============================================
# 配置管理
# ============================================

@router.get("/api/hotspot/settings")
def get_settings(_: dict = Depends(security.require_permission("hotspot"))) -> dict:
    """获取热搜监控配置"""
    row = db.fetch_one("SELECT * FROM finvue_hotspot_settings WHERE id = 'default'")
    if not row:
        # 返回默认配置
        return {
            "ok": True,
            "settings": {
                "enabledPlatforms": ["weibo", "zhihu", "baidu", "douyin", "bilibili", "toutiao", "cls", "wallstreetcn"],
                "trackedKeywords": [],
                "fetchIntervalMinutes": 60,
                "retentionDays": 30,
                "autoAnalyze": False,
            }
        }
    return {
        "ok": True,
        "settings": {
            "enabledPlatforms": parse_json(row.get("enabled_platforms"), []),
            "trackedKeywords": parse_json(row.get("tracked_keywords"), []),
            "fetchIntervalMinutes": row.get("fetch_interval_minutes") or 60,
            "retentionDays": row.get("retention_days") or 30,
            "autoAnalyze": bool(row.get("auto_analyze")),
        }
    }


@router.put("/api/hotspot/settings")
async def update_settings(request: Request, _: dict = Depends(security.require_permission("hotspot"))) -> dict:
    """更新热搜监控配置"""
    body = await request.json()
    enabled_platforms = parse_json(body.get("enabledPlatforms"), [])
    tracked_keywords = parse_json(body.get("trackedKeywords"), [])
    fetch_interval = int(body.get("fetchIntervalMinutes") or 60)
    retention_days = int(body.get("retentionDays") or 30)
    auto_analyze = bool(body.get("autoAnalyze"))

    db.execute(
        """
        INSERT INTO finvue_hotspot_settings (id, enabled_platforms, tracked_keywords, fetch_interval_minutes, retention_days, auto_analyze)
        VALUES ('default', %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            enabled_platforms = VALUES(enabled_platforms),
            tracked_keywords = VALUES(tracked_keywords),
            fetch_interval_minutes = VALUES(fetch_interval_minutes),
            retention_days = VALUES(retention_days),
            auto_analyze = VALUES(auto_analyze)
        """,
        (_json(enabled_platforms), _json(tracked_keywords), fetch_interval, retention_days, auto_analyze)
    )
    return {"ok": True, "message": "配置已更新"}


# ============================================
# 热搜数据查询
# ============================================

@router.get("/api/hotspot/current")
def get_current_hotspots(
    platform: str = Query("", alias="platform"),
    keyword: str = Query("", alias="keyword"),
    _: dict = Depends(security.require_permission("hotspot"))
) -> dict:
    """获取当前热搜榜（实时数据）"""
    where_clauses = ["last_seen_at >= DATE_SUB(NOW(), INTERVAL 2 HOUR)"]
    args: list[Any] = []

    if platform:
        where_clauses.append("platform = %s")
        args.append(platform)

    if keyword:
        where_clauses.append("title LIKE %s")
        args.append(f"%{keyword}%")

    where_sql = " AND ".join(where_clauses)

    rows = db.fetch_all(
        f"""
        SELECT id, platform, title, url, `rank`, hot_value, keywords, first_seen_at, last_seen_at, appearance_count, ai_analysis
        FROM finvue_hotspot_items
        WHERE {where_sql}
        ORDER BY platform ASC, `rank` ASC
        LIMIT 200
        """,
        tuple(args)
    )

    items = [
        {
            "id": row["id"],
            "platform": row["platform"],
            "title": row["title"],
            "url": row.get("url") or "",
            "rank": row.get("rank") or 0,
            "hotValue": row.get("hot_value") or "",
            "keywords": parse_json(row.get("keywords"), []),
            "firstSeenAt": iso(row.get("first_seen_at")),
            "lastSeenAt": iso(row.get("last_seen_at")),
            "appearanceCount": row.get("appearance_count") or 1,
            "aiAnalysis": row.get("ai_analysis") or "",
        }
        for row in rows
    ]

    # 按平台分组
    by_platform: dict[str, list[dict]] = {}
    for item in items:
        p = item["platform"]
        if p not in by_platform:
            by_platform[p] = []
        by_platform[p].append(item)

    return {"ok": True, "items": items, "byPlatform": by_platform, "total": len(items)}


@router.get("/api/hotspot/history")
def get_history_hotspots(
    platform: str = Query("", alias="platform"),
    keyword: str = Query("", alias="keyword"),
    start_date: str = Query("", alias="startDate"),
    end_date: str = Query("", alias="endDate"),
    page: int = Query(1, alias="page"),
    page_size: int = Query(20, alias="pageSize"),
    _: dict = Depends(security.require_permission("hotspot"))
) -> dict:
    """获取历史热搜数据（用于趋势对比）"""
    page, page_size = paginate(page, page_size)

    where_clauses = []
    args: list[Any] = []

    if platform:
        where_clauses.append("platform = %s")
        args.append(platform)

    if keyword:
        where_clauses.append("title LIKE %s")
        args.append(f"%{keyword}%")

    if start_date:
        where_clauses.append("first_seen_at >= %s")
        args.append(start_date)

    if end_date:
        where_clauses.append("last_seen_at <= %s")
        args.append(end_date)

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    # 获取总数
    total_row = db.fetch_one(
        f"SELECT COUNT(*) AS count FROM finvue_hotspot_items WHERE {where_sql}",
        tuple(args)
    )
    total = total_row.get("count", 0) if total_row else 0

    # 获取数据
    rows = db.fetch_all(
        f"""
        SELECT id, platform, title, url, `rank`, hot_value, keywords, first_seen_at, last_seen_at, appearance_count, ai_analysis
        FROM finvue_hotspot_items
        WHERE {where_sql}
        ORDER BY last_seen_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(args + [page_size, (page - 1) * page_size])
    )

    items = [
        {
            "id": row["id"],
            "platform": row["platform"],
            "title": row["title"],
            "url": row.get("url") or "",
            "rank": row.get("rank") or 0,
            "hotValue": row.get("hot_value") or "",
            "keywords": parse_json(row.get("keywords"), []),
            "firstSeenAt": iso(row.get("first_seen_at")),
            "lastSeenAt": iso(row.get("last_seen_at")),
            "appearanceCount": row.get("appearance_count") or 1,
            "aiAnalysis": row.get("ai_analysis") or "",
        }
        for row in rows
    ]

    return {"ok": True, "items": items, "total": total, "page": page, "pageSize": page_size}


@router.get("/api/hotspot/trend")
def get_trend_data(
    item_id: str = Query("", alias="itemId"),
    _: dict = Depends(security.require_permission("hotspot"))
) -> dict:
    """获取单个热搜的历史趋势数据（排名变化曲线）"""
    if not item_id:
        raise HTTPException(status_code=400, detail="缺少热搜条目ID")

    # 获取热搜基本信息
    item_row = db.fetch_one(
        "SELECT * FROM finvue_hotspot_items WHERE id = %s",
        (item_id,)
    )
    if not item_row:
        raise HTTPException(status_code=404, detail="热搜条目不存在")

    # 获取历史快照
    snapshots = db.fetch_all(
        """
        SELECT id, `rank`, hot_value, snapshot_time
        FROM finvue_hotspot_snapshots
        WHERE item_id = %s
        ORDER BY snapshot_time ASC
        """,
        (item_id,)
    )

    trend_data = [
        {
            "time": iso(row.get("snapshot_time")),
            "rank": row.get("rank") or 0,
            "hotValue": row.get("hot_value") or "",
        }
        for row in snapshots
    ]

    return {
        "ok": True,
        "item": {
            "id": item_row["id"],
            "platform": item_row["platform"],
            "title": item_row["title"],
            "url": item_row.get("url") or "",
            "rank": item_row.get("rank") or 0,
            "hotValue": item_row.get("hot_value") or "",
            "keywords": parse_json(item_row.get("keywords"), []),
            "firstSeenAt": iso(item_row.get("first_seen_at")),
            "lastSeenAt": iso(item_row.get("last_seen_at")),
            "appearanceCount": item_row.get("appearance_count") or 1,
            "aiAnalysis": item_row.get("ai_analysis") or "",
        },
        "trend": trend_data,
    }


@router.get("/api/hotspot/search")
def search_hotspots(
    keyword: str = Query("", alias="keyword"),
    platform: str = Query("", alias="platform"),
    days: int = Query(7, alias="days"),
    _: dict = Depends(security.require_permission("hotspot"))
) -> dict:
    """关键词搜索热搜"""
    if not keyword:
        return {"ok": True, "items": [], "total": 0}

    where_clauses = ["title LIKE %s", "last_seen_at >= DATE_SUB(NOW(), INTERVAL %s DAY)"]
    args: list[Any] = [f"%{keyword}%", days]

    if platform:
        where_clauses.append("platform = %s")
        args.append(platform)

    where_sql = " AND ".join(where_clauses)

    rows = db.fetch_all(
        f"""
        SELECT id, platform, title, url, `rank`, hot_value, keywords, first_seen_at, last_seen_at, appearance_count, ai_analysis
        FROM finvue_hotspot_items
        WHERE {where_sql}
        ORDER BY last_seen_at DESC, `rank` ASC
        LIMIT 100
        """,
        tuple(args)
    )

    items = [
        {
            "id": row["id"],
            "platform": row["platform"],
            "title": row["title"],
            "url": row.get("url") or "",
            "rank": row.get("rank") or 0,
            "hotValue": row.get("hot_value") or "",
            "keywords": parse_json(row.get("keywords"), []),
            "firstSeenAt": iso(row.get("first_seen_at")),
            "lastSeenAt": iso(row.get("last_seen_at")),
            "appearanceCount": row.get("appearance_count") or 1,
            "aiAnalysis": row.get("ai_analysis") or "",
        }
        for row in rows
    ]

    return {"ok": True, "items": items, "total": len(items), "keyword": keyword}


# ============================================
# AI 分析
# ============================================

@router.post("/api/hotspot/analyze")
async def analyze_hotspot(
    request: Request,
    session: dict = Depends(security.require_permission("hotspot"))
) -> dict:
    """AI 分析单个热搜"""
    body = await request.json()
    item_id = text(body.get("itemId") or body.get("id"))
    title = text(body.get("title"))
    platform = text(body.get("platform"))

    if not item_id and not title:
        raise HTTPException(status_code=400, detail="缺少热搜条目ID或标题")

    # 如果有 item_id，从数据库获取完整信息
    if item_id:
        row = db.fetch_one(
            "SELECT * FROM finvue_hotspot_items WHERE id = %s",
            (item_id,)
        )
        if not row:
            raise HTTPException(status_code=404, detail="热搜条目不存在")
        title = row["title"]
        platform = row["platform"]
        hot_value = row.get("hot_value") or ""
    else:
        hot_value = ""

    # AI 分析提示词
    system_prompt = """你是财经直播内容专家。你需要分析热搜话题，为直播主播提供：
1. 热点解读：用通俗语言解释这个热点事件的核心内容和影响
2. 投资关联：分析该热点可能影响的板块、个股或投资方向
3. 直播话术建议：提供3-5条可以在直播中使用的开场白、过渡语或解读框架
4. 合规提醒：指出直播讨论该话题时需要注意的合规边界
5. 互动建议：建议可以引发观众互动的问题或话题角度"""

    user_prompt = f"""请分析以下热搜话题：

平台：{platform}
标题：{title}
热度值：{hot_value}

请输出结构化的分析报告，包含：
1. 热点解读（100字以内）
2. 投资关联（涉及的板块/方向）
3. 直播话术建议（3-5条具体话术）
4. 合规提醒（注意事项）
5. 互动建议（可以问观众的问题）

输出格式使用 Markdown。"""

    # 调用 AI
    ai_result = ai_router.generate(
        {
            "systemPrompt": system_prompt,
            "userPrompt": user_prompt,
        },
        username=str(session.get("username") or ""),
    )

    analysis_text = ai_result.get("markdown") or ""

    # 如果有 item_id，保存分析结果
    if item_id:
        db.execute(
            """
            UPDATE finvue_hotspot_items
            SET ai_analysis = %s, ai_analyzed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (analysis_text, item_id)
        )

    return {
        "ok": True,
        "itemId": item_id,
        "title": title,
        "platform": platform,
        "analysis": analysis_text,
        "aiMeta": ai_result.get("aiMeta"),
    }


# ============================================
# 热搜抓取（管理员权限）
# ============================================

@router.post("/api/hotspot/fetch")
async def fetch_hotspots(
    request: Request,
    session: dict = Depends(security.require_permission("hotspot"))
) -> dict:
    """手动触发热搜抓取"""
    body = await request.json()
    platforms = parse_json(body.get("platforms"), [])

    # 如果没有指定平台，使用配置中的启用平台
    if not platforms:
        settings_row = db.fetch_one("SELECT enabled_platforms FROM finvue_hotspot_settings WHERE id = 'default'")
        if settings_row:
            platforms = parse_json(settings_row.get("enabled_platforms"), [])

    if not platforms:
        platforms = ["weibo", "zhihu", "baidu", "douyin", "bilibili", "toutiao", "cls", "wallstreetcn"]

    # 调用抓取服务
    from services.hotspot_fetcher import fetch_all_platforms
    result = await fetch_all_platforms(platforms)

    # 记录操作日志
    username = str(session.get("username") or "")
    db.execute(
        """
        INSERT INTO finvue_action_logs (username, action, detail, created_at)
        VALUES (%s, 'hotspot_fetch', %s, CURRENT_TIMESTAMP)
        """,
        (username, f"手动抓取热搜，平台: {','.join(platforms)}")
    )

    return {"ok": True, "message": "热搜抓取完成", "result": result}


# ============================================
# 数据清理（内部调用）
# ============================================

def cleanup_old_data(retention_days: int = 30) -> dict:
    """清理超过保留天数的历史数据"""
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    cutoff_str = cutoff_date.strftime("%Y-%m-%d %H:%M:%S")

    # 删除旧的热搜条目
    items_deleted = db.execute(
        "DELETE FROM finvue_hotspot_items WHERE last_seen_at < %s",
        (cutoff_str,)
    )

    # 快照表会通过外键自动删除

    return {"ok": True, "itemsDeleted": items_deleted or 0, "cutoffDate": cutoff_str}


@router.post("/api/hotspot/cleanup")
def trigger_cleanup(_: dict = Depends(security.require_permission("admin-api"))) -> dict:
    """手动触发数据清理（管理员）"""
    settings_row = db.fetch_one("SELECT retention_days FROM finvue_hotspot_settings WHERE id = 'default'")
    retention_days = settings_row.get("retention_days") if settings_row else 30
    return cleanup_old_data(retention_days)


# ============================================
# 统计数据
# ============================================

@router.get("/api/hotspot/stats")
def get_stats(_: dict = Depends(security.require_permission("hotspot"))) -> dict:
    """获取热搜统计数据"""
    # 今日新增
    today_new = db.fetch_one(
        "SELECT COUNT(*) AS count FROM finvue_hotspot_items WHERE first_seen_at >= CURDATE()"
    )

    # 当前活跃
    active = db.fetch_one(
        "SELECT COUNT(*) AS count FROM finvue_hotspot_items WHERE last_seen_at >= DATE_SUB(NOW(), INTERVAL 2 HOUR)"
    )

    # 已分析
    analyzed = db.fetch_one(
        "SELECT COUNT(*) AS count FROM finvue_hotspot_items WHERE ai_analysis IS NOT NULL AND ai_analysis != ''"
    )

    # 各平台统计
    platform_stats = db.fetch_all(
        """
        SELECT platform, COUNT(*) AS count
        FROM finvue_hotspot_items
        WHERE last_seen_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        GROUP BY platform
        """
    )

    # 最近追踪的关键词命中
    settings_row = db.fetch_one("SELECT tracked_keywords FROM finvue_hotspot_settings WHERE id = 'default'")
    tracked_keywords = parse_json(settings_row.get("tracked_keywords") if settings_row else None, [])

    keyword_hits = []
    if tracked_keywords:
        for kw in tracked_keywords:
            hit_count = db.fetch_one(
                "SELECT COUNT(*) AS count FROM finvue_hotspot_items WHERE title LIKE %s AND last_seen_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)",
                (f"%{kw}%",)
            )
            keyword_hits.append({"keyword": kw, "count": hit_count.get("count", 0) if hit_count else 0})

    return {
        "ok": True,
        "stats": {
            "todayNew": today_new.get("count", 0) if today_new else 0,
            "active": active.get("count", 0) if active else 0,
            "analyzed": analyzed.get("count", 0) if analyzed else 0,
            "platformStats": {row["platform"]: row["count"] for row in platform_stats},
            "keywordHits": keyword_hits,
        }
    }