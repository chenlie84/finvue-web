from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import ai_router
import db
import security
import store


router = APIRouter()


@router.get("/api/anchor-profiles")
def get_anchor_profiles(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", _: dict = Depends(security.require_permission("anchor-library"))) -> dict:
    return store.get_anchor_profiles(page, pageSize, q)


@router.post("/api/anchor-profiles")
async def post_anchor_profiles(request: Request, _: dict = Depends(security.require_permission("anchor-library"))) -> dict:
    return store.save_anchor_profiles(await request.json())


@router.get("/api/anchor-roi-settings")
def get_anchor_roi(_: dict = Depends(security.require_permission("portrait"))) -> dict:
    return store.get_anchor_roi_settings()


@router.put("/api/anchor-roi-settings")
async def put_anchor_roi(request: Request, _: dict = Depends(security.require_permission("portrait"))) -> dict:
    return store.save_anchor_roi_settings(await request.json())


@router.get("/api/compliance-library")
def get_compliance(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", _: dict = Depends(security.require_permission("compliance-library"))) -> dict:
    return store.get_compliance_library(page, pageSize, q)


@router.post("/api/compliance-library")
async def post_compliance(request: Request, _: dict = Depends(security.require_permission("compliance-library"))) -> dict:
    return store.save_compliance_library(await request.json())


@router.get("/api/case-library")
def get_cases(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", _: dict = Depends(security.require_permission("case-library"))) -> dict:
    return store.get_case_library(page, pageSize, q)


@router.post("/api/case-library")
async def post_cases(request: Request, _: dict = Depends(security.require_permission("case-library"))) -> dict:
    return store.save_case_library(await request.json())


def _extract_json_payload(text: str) -> Any:
    raw = str(text or "").strip()
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.I)
    candidate = fenced.group(1).strip() if fenced else raw
    try:
        return json.loads(candidate)
    except Exception:
        pass
    first_obj = candidate.find("{")
    last_obj = candidate.rfind("}")
    if first_obj >= 0 and last_obj > first_obj:
        try:
            return json.loads(candidate[first_obj : last_obj + 1])
        except Exception:
            pass
    first_arr = candidate.find("[")
    last_arr = candidate.rfind("]")
    if first_arr >= 0 and last_arr > first_arr:
        try:
            return json.loads(candidate[first_arr : last_arr + 1])
        except Exception:
            pass
    raise HTTPException(status_code=502, detail="AI 返回内容不是合法 JSON，请调整提取提示词后重试")


def _normalize_library_entries(kind: str, data: Any, source_name: str) -> list[dict[str, Any]]:
    raw_entries = data.get("entries") if isinstance(data, dict) else data
    if not isinstance(raw_entries, list):
        raise HTTPException(status_code=502, detail="AI 返回 JSON 缺少 entries 数组")
    now = datetime.now(timezone.utc).isoformat()
    entries: list[dict[str, Any]] = []
    for index, item in enumerate(raw_entries):
        if not isinstance(item, dict):
            continue
        if kind == "compliance":
            phrase = store.text(item.get("phrase") or item.get("original") or item.get("text") or item.get("quote"))
            context = store.text(item.get("context") or item.get("contextText") or item.get("originalContext"))
            level = store.text(item.get("level") or item.get("zone") or item.get("riskLevel")).lower()
            level = {"红区": "red", "灰区": "gray", "绿区": "green", "red": "red", "gray": "gray", "green": "green"}.get(level, level or "gray")
            if not phrase and not context:
                continue
            entries.append(
                {
                    **item,
                    "id": store.text(item.get("id")) or store._id("compliance"),
                    "level": level if level in {"red", "gray", "green"} else "gray",
                    "title": store.text(item.get("title")) or phrase[:80] or f"合规条目 {index + 1}",
                    "phrase": phrase or context[:160],
                    "context": context or phrase,
                    "reason": store.text(item.get("reason") or item.get("problem") or item.get("basis")),
                    "basis": store.text(item.get("basis") or item.get("rule")),
                    "suggestion": store.text(item.get("suggestion") or item.get("rewrite") or item.get("safeExample")),
                    "sourceFile": source_name,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
        else:
            quote = store.text(item.get("quote") or item.get("phrase") or item.get("text") or item.get("original"))
            context = store.text(item.get("context") or item.get("contextText") or item.get("originalContext"))
            if not quote and not context:
                continue
            entries.append(
                {
                    **item,
                    "id": store.text(item.get("id")) or store._id("case"),
                    "category": store.text(item.get("category") or item.get("type")) or "优秀案例",
                    "title": store.text(item.get("title")) or quote[:80] or f"案例条目 {index + 1}",
                    "phrase": quote or context[:160],
                    "quote": quote or context[:160],
                    "context": context or quote,
                    "whyItWorks": store.text(item.get("whyItWorks") or item.get("reason") or item.get("value")),
                    "reusableTemplate": store.text(item.get("reusableTemplate") or item.get("template")),
                    "sourceFile": source_name,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
    if not entries:
        raise HTTPException(status_code=502, detail="AI 未提取到可入库条目，请检查文件内容或提示词")
    return entries


@router.post("/api/library-extract")
async def extract_library_entries(request: Request, session: dict = Depends(security.require_any_permission("compliance-library", "case-library"))) -> dict:
    body = await request.json()
    kind = store.text(body.get("kind") or "compliance")
    if kind not in {"compliance", "case"}:
        raise HTTPException(status_code=400, detail="提取类型必须是 compliance 或 case")
    required_permission = "compliance-library" if kind == "compliance" else "case-library"
    if not security.has_permission(session, required_permission):
        raise HTTPException(status_code=403, detail=f"当前账号没有“{required_permission}”模块权限")
    content = store.text(body.get("content") or body.get("text"))
    if not content:
        raise HTTPException(status_code=400, detail="缺少待提取文件内容")
    prompt = store.text(body.get("prompt"))
    source_name = store.text(body.get("fileName") or body.get("sourceFile"))
    default_prompt = (
        "请从资料中提取合规库条目，只保留可用于直播合规训练的红区、灰区、绿区话术。"
        if kind == "compliance"
        else "请从资料中提取案例库条目，只保留优秀话术、优秀逻辑、优秀互动或优秀收口案例。"
    )
    schema = (
        '{"entries":[{"level":"red|gray|green","title":"标题","phrase":"话术原文","context":"完整上下文","reason":"判断原因","basis":"规则依据","suggestion":"合规替代表达"}]}'
        if kind == "compliance"
        else '{"entries":[{"category":"优秀话术|优秀逻辑|优秀互动|优秀收口","title":"标题","quote":"案例原话","context":"完整上下文","whyItWorks":"为什么值得借鉴","reusableTemplate":"可复用模板","tags":["标签"]}]}'
    )
    ai_result = ai_router.generate(
        {
            "systemPrompt": "你是严格的信息抽取引擎。只返回合法 JSON，不要输出 Markdown、解释或额外文本。",
            "userPrompt": "\n\n".join(
                [
                    prompt or default_prompt,
                    "抽取要求：宁缺毋滥；不要把目录、标题、说明文字误当成条目；必须保留完整上下文；不要编造资料中不存在的内容。",
                    f"输出 JSON Schema：{schema}",
                    f"来源文件：{source_name or '未命名文件'}",
                    f"资料全文：\n{content}",
                ]
            ),
        },
        username=str(session.get("username") or ""),
    )
    entries = _normalize_library_entries(kind, _extract_json_payload(ai_result.get("markdown") or ""), source_name)
    saved = store.append_compliance_entries(entries) if kind == "compliance" else store.append_case_entries(entries)
    return {"ok": True, "kind": kind, "entries": saved, "count": len(saved), "aiMeta": ai_result.get("aiMeta")}


@router.get("/api/transcript-library")
def get_transcripts(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", _: dict = Depends(security.require_permission("transcript-library"))) -> dict:
    return store.get_transcript_library(page, pageSize, q)


@router.post("/api/transcript-library")
async def post_transcripts(request: Request, _: dict = Depends(security.require_permission("transcript-library"))) -> dict:
    return store.save_transcript_library(await request.json())


@router.delete("/api/transcript-library")
async def delete_transcript(request: Request, id: str = Query("", alias="id"), _: dict = Depends(security.require_permission("transcript-library"))) -> dict:
    item_id = id
    anchor_name = ""
    if not item_id:
        try:
            body = await request.json()
            item_id = str(body.get("id") or "")
            anchor_name = str(body.get("anchorName") or "")
        except Exception:
            item_id = ""
            anchor_name = ""
    if anchor_name:
        return store.delete_transcripts_by_anchor(anchor_name)
    if not item_id:
        raise HTTPException(status_code=400, detail="缺少逐字稿 id")
    return store.delete_transcript(item_id)


@router.patch("/api/library-identity")
async def patch_identity(request: Request, _: dict = Depends(security.require_any_permission("anchor-library", "transcript-library", "customer-library"))) -> dict:
    body = await request.json()
    # 支持多种参数名：fromName/toName, oldName/newName, from/to
    old_name = store.text(body.get("fromName") or body.get("oldName") or body.get("from"))
    new_name = store.text(body.get("toName") or body.get("newName") or body.get("to"))
    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="缺少原名称或新名称")
    
    if old_name == new_name:
        raise HTTPException(status_code=400, detail="原名称和新名称相同")
    
    # 检查是否有数据需要改名（放宽检查条件，只要有任何相关数据即可）
    old_profile = db.fetch_one(
        "SELECT id, raw FROM finvue_anchor_profiles WHERE anchor_name = %s ORDER BY updated_at DESC LIMIT 1",
        (old_name,)
    )
    old_transcripts_count = db.fetch_one(
        "SELECT COUNT(*) as cnt FROM finvue_transcripts WHERE anchor_name = %s",
        (old_name,)
    )
    old_reports_count = db.fetch_one(
        "SELECT COUNT(*) as cnt FROM finvue_analysis_reports WHERE anchor_name = %s",
        (old_name,)
    )
    
    has_old_data = old_profile or (old_transcripts_count and old_transcripts_count.get("cnt", 0) > 0) or (old_reports_count and old_reports_count.get("cnt", 0) > 0)
    
    if not has_old_data:
        raise HTTPException(status_code=404, detail=f"未找到 '{old_name}' 的任何数据")
    
    # 检查新名称是否已存在（用于判断是否需要合并）
    new_profile = db.fetch_one("SELECT id, raw FROM finvue_anchor_profiles WHERE anchor_name = %s ORDER BY updated_at DESC LIMIT 1", (new_name,))
    
    merged = False
    
    # 如果新旧主播 profile 都存在且不同，需要合并数据
    if old_profile and new_profile and old_profile["id"] != new_profile["id"]:
        merged = True
        # 合并 snapshots
        old_raw = store.parse_json(old_profile.get("raw"), {})
        new_raw = store.parse_json(new_profile.get("raw"), {})
        
        old_snapshots = store.safe_array(old_raw.get("snapshots", []))
        new_snapshots = store.safe_array(new_raw.get("snapshots", []))
        
        # 去重合并
        merged_snapshots = []
        seen_ids = set()
        for s in new_snapshots + old_snapshots:
            sid = s.get("id") or s.get("analyzedAt") or ""
            if sid not in seen_ids:
                merged_snapshots.append(s)
                seen_ids.add(sid)
        new_raw["snapshots"] = merged_snapshots
        # 更新合并后的 profile
        db.execute(
            "UPDATE finvue_anchor_profiles SET raw = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (store._json(new_raw), new_profile["id"])
        )
        # 删除旧的 profile
        db.execute("DELETE FROM finvue_anchor_profiles WHERE id = %s", (old_profile["id"],))
    
    # 如果只有旧 profile 存在，新 profile 不存在，直接改名
    if old_profile and not new_profile:
        db.execute(
            "UPDATE finvue_anchor_profiles SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s",
            (new_name, old_name)
        )
    
    # 更新其他表中的 anchor_name
    db.execute("UPDATE finvue_transcripts SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))
    db.execute("UPDATE finvue_analysis_reports SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))
    db.execute("UPDATE finvue_customer_profiles SET latest_anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE latest_anchor_name = %s", (new_name, old_name))
    db.execute("UPDATE finvue_customer_sessions SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))
    
    # 返回更新后的数据
    profiles = db.fetch_all("SELECT raw FROM finvue_anchor_profiles ORDER BY updated_at DESC")
    entries = db.fetch_all("SELECT raw FROM finvue_transcripts ORDER BY updated_at DESC")
    
    return {
        "ok": True,
        "oldName": old_name,
        "newName": new_name,
        "merged": merged,
        "profiles": [store.parse_json(p.get("raw"), {}) for p in profiles],
        "entries": [store.parse_json(e.get("raw"), {}) for e in entries]
    }
