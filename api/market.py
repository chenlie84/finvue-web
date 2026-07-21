from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response

import ai_router
import db
import security
from services import tushare_market


router = APIRouter()


THEME_KEYWORDS = {
    "半导体": ["半导体", "芯片", "存储", "AI", "算力", "英伟达", "美光", "海力士", "长鑫"],
    "机器人": ["机器人", "人形机器人", "具身智能", "自动化", "减速器"],
    "汽车": ["汽车", "新能源车", "智能车", "小米汽车", "问界", "比亚迪", "特斯拉"],
    "医药": ["医药", "创新药", "药店", "医疗", "医保", "疫苗"],
    "黄金有色": ["黄金", "白银", "铜", "有色", "贵金属"],
    "能源化工": ["原油", "石油", "天然气", "煤炭", "化工"],
    "金融地产": ["银行", "券商", "保险", "地产", "房贷"],
    "消费": ["消费", "白酒", "食品", "零售", "旅游"],
}


def _split_codes(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_items = value
    else:
        raw_items = re.split(r"[\s,，;；]+", str(value or ""))
    result: list[str] = []
    for item in raw_items:
        code = str(item or "").strip().upper()
        if code and code not in result:
            result.append(code)
    return result


def _truthy(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "启用", "是"}


def _parse_env_config(text: str) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _pick(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    return None


def _normalize_imported_tushare_settings(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("tushare") if isinstance(raw.get("tushare"), dict) else raw
    settings = data.get("settings") if isinstance(data.get("settings"), dict) else data
    return {
        "enabled": _truthy(_pick(settings, "enabled", "schedulerEnabled", "TUSHARE_ENABLED", "TUSHARE_SCHEDULER_ENABLED"), True),
        "token": str(_pick(settings, "token", "apiKey", "TUSHARE_TOKEN", "TUSHARE_API_TOKEN") or "").strip(),
        "intervalMinutes": _pick(settings, "intervalMinutes", "interval", "TUSHARE_INTERVAL_MINUTES") or 60,
        "indexCodes": _split_codes(_pick(settings, "indexCodes", "indexes", "TUSHARE_INDEX_CODES") or tushare_market.DEFAULT_INDEX_CODES),
        "stockCodes": _split_codes(_pick(settings, "stockCodes", "stocks", "TUSHARE_STOCK_CODES") or tushare_market.DEFAULT_STOCK_CODES),
    }


def _parse_uploaded_tushare_config(content: bytes, filename: str = "") -> dict[str, Any]:
    text = content.decode("utf-8-sig").strip()
    if not text:
        raise ValueError("配置文件为空")
    if filename.lower().endswith(".json") or text[:1] in {"{", "["}:
        loaded = json.loads(text)
        if not isinstance(loaded, dict):
            raise ValueError("JSON 配置顶层必须是对象")
        return _normalize_imported_tushare_settings(loaded)
    return _normalize_imported_tushare_settings(_parse_env_config(text))


@router.get("/api/market/overview")
def overview(_: dict = Depends(security.require_permission("market"))) -> dict:
    settings = tushare_market.mask_settings()
    cache = tushare_market.get_cached_snapshot()
    if cache and "hotSectors" not in cache:
        cache = {**cache, "hotSectors": tushare_market.build_hot_sectors(cache.get("stocks") or [])}
    return {"ok": True, "settings": settings, "snapshot": cache}


@router.post("/api/market/refresh")
async def refresh(_: Request, __: dict = Depends(security.require_permission("market"))) -> dict:
    settings = tushare_market.get_settings()
    if not settings.get("token"):
        raise HTTPException(status_code=400, detail="TuShare token 未配置")
    try:
        snapshot = await asyncio.to_thread(tushare_market.fetch_market_snapshot, settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "snapshot": snapshot}


def _recent_hotspots(limit: int = 80) -> list[dict[str, Any]]:
    try:
        return db.fetch_all(
            """
            SELECT id, platform, title, url, rank, hot_value, last_seen_at
            FROM finvue_hotspot_items
            WHERE last_seen_at >= DATE_SUB(NOW(), INTERVAL 6 HOUR)
            ORDER BY
              CASE WHEN rank IS NULL OR rank = 0 THEN 999 ELSE rank END ASC,
              last_seen_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    except Exception:
        return []


def _quote_keywords(snapshot: dict[str, Any]) -> dict[str, list[str]]:
    keywords: dict[str, list[str]] = {}
    for item in (snapshot.get("indexes") or []) + (snapshot.get("stocks") or []):
        name = str(item.get("name") or item.get("code") or "").strip()
        code = str(item.get("code") or "").strip()
        if name:
            keywords[name] = [name, code.split(".")[0], code]
    for theme, words in THEME_KEYWORDS.items():
        keywords[theme] = words
    return keywords


def _match_hotspots(snapshot: dict[str, Any], hotspots: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    keyword_map = _quote_keywords(snapshot)
    matched: dict[str, list[dict[str, Any]]] = {}
    for target, words in keyword_map.items():
        hits = []
        for item in hotspots:
            title = str(item.get("title") or "")
            if any(word and word.lower() in title.lower() for word in words):
                hits.append(item)
        if hits:
            matched[target] = hits[:6]
    return matched


def _market_lines(snapshot: dict[str, Any]) -> list[str]:
    rows = []
    for group_label, items in (("指数", snapshot.get("indexes") or []), ("个股", snapshot.get("stocks") or [])):
        for item in items[:10]:
            rows.append(
                f"- [{group_label}] {item.get('name')}({item.get('code')}) "
                f"收盘 {item.get('close')}，涨跌幅 {item.get('pctChange')}%，成交额 {item.get('amount')}，交易日 {item.get('tradeDate')}"
            )
    return rows


@router.post("/api/market/ai-attribution")
async def ai_attribution(_: Request, session: dict = Depends(security.require_permission("market"))) -> dict:
    snapshot = tushare_market.get_cached_snapshot()
    if not snapshot:
        raise HTTPException(status_code=400, detail="暂无行情缓存，请先刷新行情")
    hotspots = _recent_hotspots()
    if not hotspots:
        raise HTTPException(status_code=400, detail="暂无最近热搜数据，请先刷新热点追踪")

    matched = _match_hotspots(snapshot, hotspots)
    platform_names = {
        "weibo": "微博",
        "zhihu": "知乎",
        "baidu": "百度",
        "douyin": "抖音",
        "bilibili": "B站",
        "toutiao": "头条",
        "cls": "财联社",
        "wallstreetcn": "华尔街见闻",
    }
    hot_lines = []
    for target, items in matched.items():
        hot_lines.append(f"\n【{target}】")
        for item in items:
            platform = platform_names.get(str(item.get("platform")), str(item.get("platform") or ""))
            hot_lines.append(f"- [{platform} #{item.get('rank') or '-'}] {item.get('title')}")
    if not hot_lines:
        hot_lines = ["本轮热搜未直接命中已配置指数/股票名称，仅可做宏观主题观察。"]

    system_prompt = """你是投顾团队的市场异动归因分析师和合规助手。
你需要把行情数据和消息面热搜做弱关联分析，帮助直播团队判断哪些行情可能有消息催化。
要求：
1. 必须区分“直接关联”“主题关联”“仅情绪相关”“噪音”，不要把相关性说成因果。
2. 不输出个股买卖建议、不预测涨跌、不承诺收益。
3. 给出可用于直播的解释角度和合规边界。
4. 输出简洁，适合放在行情页顶部。"""

    user_prompt = f"""【行情数据】
{chr(10).join(_market_lines(snapshot))}

【最近 6 小时热搜命中】
{chr(10).join(hot_lines)}

请输出 Markdown，结构如下：

# AI 消息面归因

## 今日最值得关注
列出 3-5 条，格式：标的/主题｜行情表现｜关联消息｜归因判断（直接/主题/情绪/噪音）｜一句话结论。

## 直播解读角度
给 3 个适合财经直播展开的角度，语言要克制。

## 合规提醒
列 2-3 条需要避开的表达。"""

    ai_result = await asyncio.to_thread(
        ai_router.generate,
        {"systemPrompt": system_prompt, "userPrompt": user_prompt},
        str(session.get("username") or ""),
    )
    return {
        "ok": True,
        "analysis": ai_result.get("markdown") or "",
        "matchedTargets": list(matched.keys()),
        "hotspotCount": len(hotspots),
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "aiMeta": ai_result.get("aiMeta"),
    }


@router.get("/api/admin/tushare")
def get_tushare_settings(_: dict = Depends(security.require_admin)) -> dict:
    return {"ok": True, "settings": tushare_market.mask_settings()}


@router.put("/api/admin/tushare")
async def put_tushare_settings(request: Request, session: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    saved = tushare_market.save_settings(incoming if isinstance(incoming, dict) else {}, session.get("username", ""))
    return {"ok": True, "settings": tushare_market.mask_settings(saved)}


@router.get("/api/admin/tushare/export")
def export_tushare_settings(_: dict = Depends(security.require_admin)) -> Response:
    settings = tushare_market.get_settings()
    payload = {
        "type": "finvue-tushare-config",
        "version": 1,
        "exportedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "tushare": {
            "enabled": settings.get("enabled"),
            "token": settings.get("token"),
            "intervalMinutes": settings.get("intervalMinutes"),
            "indexCodes": settings.get("indexCodes"),
            "stockCodes": settings.get("stockCodes"),
        },
    }
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="finvue-tushare-config.json"'},
    )


@router.get("/api/admin/tushare/template")
def export_tushare_template(_: dict = Depends(security.require_admin)) -> Response:
    payload = {
        "type": "finvue-tushare-config",
        "version": 1,
        "tushare": {
            "enabled": True,
            "token": "填入你的 TuShare Token",
            "intervalMinutes": 60,
            "indexCodes": tushare_market.DEFAULT_INDEX_CODES,
            "stockCodes": tushare_market.DEFAULT_STOCK_CODES,
        },
    }
    return Response(
        json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="finvue-tushare-config-template.json"'},
    )


@router.post("/api/admin/tushare/import")
async def import_tushare_settings(
    file: UploadFile = File(...),
    session: dict = Depends(security.require_admin),
) -> dict:
    content = await file.read()
    try:
        settings = _parse_uploaded_tushare_config(content, file.filename or "")
        current = tushare_market.get_settings()
        token = str(settings.get("token") or "").strip()
        if not token or token == "********" or token.startswith("填入"):
            settings["token"] = current.get("token", "")
        saved = tushare_market.save_settings(settings, session.get("username", ""))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"配置文件导入失败：{exc}") from exc
    return {
        "ok": True,
        "message": "TuShare 配置已导入并保存",
        "settings": tushare_market.mask_settings(saved),
        "imported": {
            "indexCount": len(saved.get("indexCodes") or []),
            "stockCount": len(saved.get("stockCodes") or []),
            "enabled": bool(saved.get("enabled")),
            "hasToken": bool(saved.get("token")),
        },
    }


@router.post("/api/admin/tushare/test")
async def test_tushare_settings(request: Request, _: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    incoming = incoming if isinstance(incoming, dict) else {}
    current = tushare_market.get_settings()
    token = str(incoming.get("token") or "")
    if token == "********":
        token = current.get("token", "")
    if not token:
        raise HTTPException(status_code=400, detail="请先填写 TuShare token")
    try:
        result = await asyncio.to_thread(tushare_market.test_token, token)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"TuShare 连接失败：{exc}") from exc
    return {"ok": True, "message": f"连接成功，交易日历返回 {result.get('rows', 0)} 条"}


@router.get("/api/admin/tushare/stocks")
def get_tushare_stocks(_: dict = Depends(security.require_admin)) -> dict:
    universe = tushare_market.get_stock_universe()
    return {"ok": True, "universe": universe}


@router.post("/api/admin/tushare/stocks/refresh")
async def refresh_tushare_stocks(_: Request, __: dict = Depends(security.require_admin)) -> dict:
    settings = tushare_market.get_settings()
    if not settings.get("token"):
        raise HTTPException(status_code=400, detail="TuShare token 未配置")
    try:
        universe = await asyncio.to_thread(tushare_market.fetch_stock_universe, settings)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"股票基础库刷新失败：{exc}") from exc
    return {"ok": True, "universe": universe}
