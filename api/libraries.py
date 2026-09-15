from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

import ai_router
import db
import security
import store


logger = logging.getLogger(__name__)

router = APIRouter()


# 运营 / SOP 表：这些表的 anchor_name 参与唯一键，改名时不能简单 UPDATE。
#
# 外键关系（`information_schema.REFERENTIAL_CONSTRAINTS` 实测）：
#   sop_action_progress.anchor_name  -> sop_anchors.anchor_name  ON DELETE CASCADE
#   sop_week_completion.anchor_name  -> sop_anchors.anchor_name  ON DELETE CASCADE
#   operation_fans_stats 无外键，独立。
#
# 元组含义：(表名, 除主播名外的其余唯一键列)
_INDEPENDENT_ANCHOR_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("finvue_operation_fans_stats", ("stat_date",)),
)
_SOP_ANCHOR_TABLE = "finvue_sop_anchors"
_SOP_CHILD_TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("finvue_sop_action_progress", ("week", "action_index", "sub_index", "child_index")),
    ("finvue_sop_week_completion", ("week",)),
)


def _table_has_column(table: str, column: str) -> bool:
    """表里有没有这一列。用于给「有 / 没有 updated_at」的表生成不同 SQL。"""
    row = db.fetch_one(
        "SELECT 1 AS x FROM information_schema.COLUMNS"
        " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s LIMIT 1",
        (table, column),
    )
    return bool(row)


def _drop_colliding_rows(table: str, old_name: str, new_name: str, key_cols: tuple[str, ...]) -> int:
    """删掉 old 中「改完会跟 new 撞唯一键」的行。

    语义上两边是同一个人的同一条记录，所以「目标优先」：new 已有同键行时丢弃 old 的。
    先删冲突行，剩下的 UPDATE 才不会触发 Duplicate entry。
    """
    if not key_cols:
        if db.fetch_one(
            f"SELECT 1 AS x FROM {table} WHERE anchor_name = %s LIMIT 1", (new_name,)
        ):
            return db.execute(f"DELETE FROM {table} WHERE anchor_name = %s", (old_name,)) or 0
        return 0
    condition = " AND ".join(f"o.`{col}` <=> n.`{col}`" for col in key_cols)
    return db.execute(
        f"DELETE o FROM {table} o JOIN {table} n"
        f" ON n.anchor_name = %s AND {condition}"
        f" WHERE o.anchor_name = %s",
        (new_name, old_name),
    ) or 0


def _fork_sop_anchor_row(source: str, target: str) -> bool:
    """确保 sop_anchors 里存在 target 行，不存在就从 source 复制一份。

    子表的外键指向 sop_anchors，所以必须先有目标父行，子表才能改过去；
    又不能直接改父行的名字 —— 外键是 ON UPDATE NO ACTION，父行一改就违反约束。
    列名从 information_schema 现取，避免以后加字段时这里漏写。
    """
    if db.fetch_one(
        f"SELECT 1 AS x FROM {_SOP_ANCHOR_TABLE} WHERE anchor_name = %s LIMIT 1", (target,)
    ):
        return False
    cols = [
        row["COLUMN_NAME"]
        for row in db.fetch_all(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS"
            " WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION",
            (_SOP_ANCHOR_TABLE,),
        )
        if row.get("COLUMN_NAME") and row["COLUMN_NAME"] != "anchor_name"
    ]
    if not cols:
        raise RuntimeError(f"{_SOP_ANCHOR_TABLE} 除 anchor_name 外没有其他列，无法复制")
    col_sql = ", ".join(f"`{col}`" for col in cols)
    db.execute(
        f"INSERT INTO {_SOP_ANCHOR_TABLE} (anchor_name, {col_sql})"
        f" SELECT %s, {col_sql} FROM {_SOP_ANCHOR_TABLE} WHERE anchor_name = %s",
        (target, source),
    )
    return True


def _rename_sop_family(old_name: str, new_name: str) -> dict[str, int]:
    """SOP 三张表（父表 + 两张 ON DELETE CASCADE 子表）。

    ⚠️ 执行顺序不能变，反了会**静默丢数据**：
    第一版先删父表的旧行，级联把该主播在子表里还没搬走的行一起删了
    （实测 week=2 那行就这么没了），而且不报错。
    正确顺序固定为：确保目标父行存在 → 迁子表 → 最后才删源父行（此时已无子行可级联）。
    """
    result: dict[str, int] = {}
    forked = _fork_sop_anchor_row(old_name, new_name)
    for table, key_cols in _SOP_CHILD_TABLES:
        _drop_colliding_rows(table, old_name, new_name, key_cols)
        set_clause = "anchor_name = %s"
        if _table_has_column(table, "updated_at"):
            set_clause += ", updated_at = CURRENT_TIMESTAMP"
        result[table] = db.execute(
            f"UPDATE {table} SET {set_clause} WHERE anchor_name = %s", (new_name, old_name)
        ) or 0
    removed = db.execute(
        f"DELETE FROM {_SOP_ANCHOR_TABLE} WHERE anchor_name = %s", (old_name,)
    ) or 0
    result[_SOP_ANCHOR_TABLE] = removed
    logger.info(
        "[library-identity] SOP 改名 %s -> %s，forked=%s，明细=%s",
        old_name, new_name, forked, result,
    )
    return result


def _rename_aux_anchor_tables(old_name: str, new_name: str) -> dict[str, int]:
    """把运营 / SOP 表里的主播名从 old_name 改成 new_name。

    这几张表的 anchor_name 参与唯一键，目标名已存在同键行时直接 UPDATE 会抛
    Duplicate entry，把整个改名请求打成 500，所以都要「先删冲突行再改」。
    单表失败只记日志，不影响主流程 —— 主播档案 / 逐字稿 / 报告那几张核心表已经更新完了。
    """
    moved: dict[str, int] = {}
    for table, key_cols in _INDEPENDENT_ANCHOR_TABLES:
        try:
            _drop_colliding_rows(table, old_name, new_name, key_cols)
            set_clause = "anchor_name = %s"
            if _table_has_column(table, "updated_at"):
                set_clause += ", updated_at = CURRENT_TIMESTAMP"
            moved[table] = db.execute(
                f"UPDATE {table} SET {set_clause} WHERE anchor_name = %s", (new_name, old_name)
            ) or 0
        except Exception:
            logger.exception("[library-identity] 更新 %s 失败（已跳过）", table)
            moved[table] = -1

    try:
        moved.update(_rename_sop_family(old_name, new_name))
    except Exception:
        logger.exception("[library-identity] SOP 表改名失败（已跳过）")
    return moved


@router.get("/api/anchor-profiles")
def get_anchor_profiles(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", _: dict = Depends(security.require_permission("anchor-library"))) -> dict:
    return store.get_anchor_profiles(page, pageSize, q)


@router.post("/api/anchor-profiles")
async def post_anchor_profiles(request: Request, _: dict = Depends(security.require_permission("anchor-library"))) -> dict:
    return store.save_anchor_profiles(await request.json())


@router.delete("/api/anchor-profiles")
async def delete_anchor_profile(request: Request, _: dict = Depends(security.require_permission("anchor-library"))) -> dict:
    """删除主播及其所有关联数据：逐字稿、分析报告、合规库、案例库."""
    body = await request.json()
    anchor_id = store.text(body.get("id") or body.get("anchorId"))
    anchor_name = store.text(body.get("anchorName") or body.get("name"))
    if not anchor_id and not anchor_name:
        raise HTTPException(status_code=400, detail="缺少主播 ID 或名称")
    return store.delete_anchor_profile(anchor_id or "", anchor_name or "")


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
    old_name = store.text(body.get("fromName") or body.get("oldName") or body.get("from"))
    new_name = store.text(body.get("toName") or body.get("newName") or body.get("to"))

    if not old_name or not new_name:
        raise HTTPException(status_code=400, detail="缺少原名称或新名称")

    if old_name == new_name:
        raise HTTPException(status_code=400, detail="原名称和新名称相同")

    # 获取所有 old_name 的 profile（可能有多条重复记录）
    old_profiles = db.fetch_all(
        "SELECT id, raw, updated_at FROM finvue_anchor_profiles WHERE anchor_name = %s ORDER BY updated_at DESC",
        (old_name,)
    )
    # 获取所有 new_name 的 profile（可能有多条重复记录）
    new_profiles = db.fetch_all(
        "SELECT id, raw, updated_at FROM finvue_anchor_profiles WHERE anchor_name = %s ORDER BY updated_at DESC",
        (new_name,)
    )

    # 检查是否有其他数据（transcripts, reports）
    old_transcripts_count = db.fetch_one("SELECT COUNT(*) as cnt FROM finvue_transcripts WHERE anchor_name = %s", (old_name,))
    old_reports_count = db.fetch_one("SELECT COUNT(*) as cnt FROM finvue_analysis_reports WHERE anchor_name = %s", (old_name,))

    has_old_data = old_profiles or (old_transcripts_count and old_transcripts_count.get("cnt", 0) > 0) or (old_reports_count and old_reports_count.get("cnt", 0) > 0)

    # 先执行所有数据表的更新（确保在所有情况下都能同步）
    # 更新逐字稿表的 anchor_name 字段
    db.execute("UPDATE finvue_transcripts SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))
    # 更新分析报告表
    db.execute("UPDATE finvue_analysis_reports SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))
    # 更新客户表
    db.execute("UPDATE finvue_customer_profiles SET latest_anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE latest_anchor_name = %s", (new_name, old_name))
    db.execute("UPDATE finvue_customer_sessions SET anchor_name = %s, updated_at = CURRENT_TIMESTAMP WHERE anchor_name = %s", (new_name, old_name))

    # 运营 / SOP 表：anchor_name 参与唯一键，需要特殊处理键冲突（详见函数注释）
    aux_moved = _rename_aux_anchor_tables(old_name, new_name)

    # 同步更新逐字稿 raw JSON 中的 anchorName
    # 查询所有 anchor_name = new_name 的逐字稿（包括原本就是 new_name 的和新更新的）
    all_transcripts_with_new_name = db.fetch_all("SELECT id, raw FROM finvue_transcripts WHERE anchor_name = %s", (new_name,))
    for t in all_transcripts_with_new_name:
        raw = store.parse_json(t.get("raw"), {})
        if raw.get("anchorName") != new_name:
            raw["anchorName"] = new_name
            db.execute("UPDATE finvue_transcripts SET raw = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (store._json(raw), t["id"]))

    # 同步更新分析报告 raw JSON 中的 anchorName
    all_reports_with_new_name = db.fetch_all("SELECT id, raw FROM finvue_analysis_reports WHERE anchor_name = %s", (new_name,))
    for r in all_reports_with_new_name:
        raw = store.parse_json(r.get("raw"), {})
        if raw.get("anchorName") != new_name:
            raw["anchorName"] = new_name
            db.execute("UPDATE finvue_analysis_reports SET raw = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (store._json(raw), r["id"]))

    # 合并主播资料库
    all_profiles_to_merge = old_profiles + new_profiles
    if all_profiles_to_merge:
        # 选主记录要跟注释口径一致：优先用「目标名」那条 —— 它是用户选定的规范名，
        # 可能已经攒了快照，比旧名那条更该保留。
        # 原实现写的是 all_profiles_to_merge[0]，而 old_profiles 拼在前面，
        # 所以取到的永远是旧名那条，跟注释恰好相反。
        main_profile = new_profiles[0] if new_profiles else old_profiles[0]
        main_raw = store.parse_json(main_profile.get("raw"), {})
        main_raw["anchorName"] = new_name

        # 合并所有 snapshots，去重
        all_snapshots = []
        seen_ids = set()
        for p in all_profiles_to_merge:
            raw = store.parse_json(p.get("raw"), {})
            for s in store.safe_array(raw.get("snapshots", [])):
                sid = s.get("id") or s.get("analyzedAt") or ""
                if sid and sid not in seen_ids:
                    all_snapshots.append(s)
                    seen_ids.add(sid)

        main_raw["snapshots"] = all_snapshots

        # 更新主记录
        db.execute(
            "UPDATE finvue_anchor_profiles SET anchor_name = %s, raw = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (new_name, store._json(main_raw), main_profile["id"])
        )

        # 删除其他所有重复记录
        for p in all_profiles_to_merge[1:]:
            db.execute("DELETE FROM finvue_anchor_profiles WHERE id = %s", (p["id"],))
    elif not has_old_data:
        # 如果没有任何 old_name 的数据，也没有 new_name 的主播资料，创建新的主播资料
        now = datetime.now(timezone.utc).isoformat()
        new_id = store._id("anchor")
        new_raw = {"id": new_id, "anchorName": new_name, "snapshots": [], "createdAt": now, "updatedAt": now}
        db.execute(
            "INSERT INTO finvue_anchor_profiles (id, anchor_name, raw, created_at, updated_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (new_id, new_name, store._json(new_raw))
        )
    else:
        # 有逐字稿/报告数据但没有主播资料，创建新的主播资料
        now = datetime.now(timezone.utc).isoformat()
        new_id = store._id("anchor")
        new_raw = {"id": new_id, "anchorName": new_name, "snapshots": [], "createdAt": now, "updatedAt": now}
        db.execute(
            "INSERT INTO finvue_anchor_profiles (id, anchor_name, raw, created_at, updated_at) VALUES (%s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (new_id, new_name, store._json(new_raw))
        )

    # 返回更新后的数据
    profiles = db.fetch_all("SELECT raw FROM finvue_anchor_profiles ORDER BY updated_at DESC")
    entries = db.fetch_all("SELECT raw FROM finvue_transcripts ORDER BY updated_at DESC")

    return {
        "ok": True,
        "oldName": old_name,
        "newName": new_name,
        # 运营 / SOP 表的改名明细（表名 -> 影响行数，-1 表示该表失败已跳过）。
        # 之前只写进日志，接口不回传，前端无从知道这几张表到底改没改。
        "auxTables": aux_moved,
        "profiles": [store.parse_json(p.get("raw"), {}) for p in profiles],
        "entries": [store.parse_json(e.get("raw"), {}) for e in entries]
    }

