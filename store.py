"""MySQL-backed repositories for FinVue FastAPI runtime."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import db


DEFAULT_SETTINGS: dict[str, Any] = {
    "promptPreset": "custom",
    "liveType": "advisory",
    "aiProviders": [
        {
            "id": "primary-volcengine",
            "label": "火山主路由",
            "baseUrl": "https://ark.cn-beijing.volces.com/api/v3/responses",
            "apiKey": "",
            "model": "doubao-seed-2-0-pro-250415",
            "enabled": True,
            "priority": 1,
        }
    ],
    "anchorRolePrompt": "你是一位资深的抖音直播运营分析专家和合规顾问，重点从直播结构、互动效率、合规边界、用户理解度和转化动作五个方面评估主播表现，并给出可直接复用的优化建议。",
    "systemPrompt": "你是一位资深的抖音直播运营分析专家和合规顾问。所有结论必须引用原始数据或逐字稿证据，输出 Markdown，建议要具体可执行。",
    "userPrompt": "请基于完整直播数据和逐字稿，生成一份结构化直播分析报告，覆盖直播概况、合规风险、内容结构、互动承接、转化动作、主播画像和改进建议。",
    "reportFormat": "输出 Markdown，标题清晰，表格优先，结论必须引用原始数据。",
    "externalHotTopics": "",
}

PERMISSION_KEYS = [
    "home",
    "live",
    "anchor-library",
    "customer-library",
    "transcript-library",
    "distill-library",
    "sop",
    "compliance-library",
    "case-library",
    "portrait",
    "hotspot",
    "market",
    "research",
    "backtest",
    "export",
    "notify",
    "admin-api",
]


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


def iso(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def text(value: Any) -> str:
    return str(value or "").strip()


def to_int(value: Any, default: int = 0) -> int:
    raw = str(value or "").replace(",", "").strip()
    if not raw:
        return default
    import re

    match = re.search(r"-?\d+(\.\d+)?", raw)
    if not match:
        return default
    try:
        return int(float(match.group(0)))
    except Exception:
        return default


def safe_array(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def safe_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def normalize_user_permissions(role: str = "user", permissions: Any = None) -> dict[str, bool]:
    if role == "admin":
        return {key: True for key in PERMISSION_KEYS}
    raw = safe_object(permissions)
    return {key: bool(raw.get(key)) for key in PERMISSION_KEYS}


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def _dt(value: Any) -> str | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    raw = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def paginate(page: int = 1, page_size: int = 20) -> tuple[int, int]:
    page = max(1, int(page or 1))
    page_size = min(100, max(1, int(page_size or 20)))
    return page, page_size


def get_kv(key: str, fallback: Any = None) -> Any:
    row = db.fetch_one("SELECT value FROM finvue_app_kv WHERE `key` = %s", (key,))
    return parse_json(row.get("value") if row else None, fallback)


def set_kv(key: str, value: Any) -> Any:
    db.execute(
        """
        INSERT INTO finvue_app_kv (`key`, value, updated_at)
        VALUES (%s, %s, CURRENT_TIMESTAMP)
        ON DUPLICATE KEY UPDATE value = VALUES(value), updated_at = CURRENT_TIMESTAMP
        """,
        (key, _json(value)),
    )
    return value


def get_settings() -> dict[str, Any]:
    saved = get_kv("settings", {})
    return {**DEFAULT_SETTINGS, **safe_object(saved)}


def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    value = {**DEFAULT_SETTINGS, **safe_object(payload), "updatedAt": datetime.now(timezone.utc).isoformat()}
    return set_kv("settings", value)


def get_user_ai_settings(username: str) -> dict[str, Any]:
    key = f"user-ai-settings:{text(username).lower()}"
    saved = get_kv(key, {})
    return safe_object(saved)


def save_user_ai_settings(username: str, payload: dict[str, Any]) -> dict[str, Any]:
    key = f"user-ai-settings:{text(username).lower()}"
    value = {
        "aiProviders": safe_array(payload.get("aiProviders")),
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }
    return set_kv(key, value)


def get_effective_settings(username: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    if not username:
        return settings
    user_settings = get_user_ai_settings(username)
    providers = safe_array(user_settings.get("aiProviders"))
    if providers:
        return {**settings, "aiProviders": providers, "userAiSettings": user_settings}
    return settings


def list_users() -> list[dict[str, Any]]:
    rows = db.fetch_all(
        """
        SELECT username, role, permissions, created_at, password_salt, password_hash
        FROM finvue_users
        ORDER BY username ASC
        """
    )
    return [
        {
            "username": row["username"],
            "role": row.get("role") or "user",
            "permissions": normalize_user_permissions(row.get("role") or "user", parse_json(row.get("permissions"), {})),
            "createdAt": iso(row.get("created_at")),
            "passwordSalt": row.get("password_salt"),
            "passwordHash": row.get("password_hash"),
        }
        for row in rows
    ]


def get_user_by_username(username: str) -> dict[str, Any] | None:
    row = db.fetch_one(
        """
        SELECT username, role, permissions, created_at, password_salt, password_hash
        FROM finvue_users
        WHERE username = %s
        """,
        (str(username or "").strip().lower(),),
    )
    if not row:
        return None
    return {
        "username": row["username"],
        "role": row.get("role") or "user",
        "permissions": normalize_user_permissions(row.get("role") or "user", parse_json(row.get("permissions"), {})),
        "createdAt": iso(row.get("created_at")),
        "passwordSalt": row.get("password_salt"),
        "passwordHash": row.get("password_hash"),
    }


def save_user(user: dict[str, Any]) -> dict[str, Any]:
    username = str(user.get("username") or "").strip().lower()
    role = user.get("role") or "user"
    permissions = normalize_user_permissions(role, user.get("permissions"))
    db.execute(
        """
        INSERT INTO finvue_users (username, role, permissions, password_salt, password_hash, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP), CURRENT_TIMESTAMP)
        ON DUPLICATE KEY UPDATE
          role = VALUES(role),
          permissions = VALUES(permissions),
          password_salt = VALUES(password_salt),
          password_hash = VALUES(password_hash),
          updated_at = CURRENT_TIMESTAMP
        """,
        (
            username,
            role,
            _json(permissions),
            user.get("passwordSalt") or user.get("password_salt"),
            user.get("passwordHash") or user.get("password_hash"),
            _dt(user.get("createdAt")),
        ),
    )
    saved = get_user_by_username(username)
    if not saved:
        raise RuntimeError("用户保存失败")
    return saved


def update_user_role(username: str, role: str) -> dict[str, Any] | None:
    db.execute(
        "UPDATE finvue_users SET role = %s, permissions = %s, updated_at = CURRENT_TIMESTAMP WHERE username = %s",
        (role, _json(normalize_user_permissions(role)), username),
    )
    return get_user_by_username(username)


def update_user_permissions(username: str, permissions: Any) -> dict[str, Any] | None:
    user = get_user_by_username(username)
    if not user:
        return None
    next_permissions = normalize_user_permissions(user.get("role", "user"), permissions)
    db.execute("UPDATE finvue_users SET permissions = %s, updated_at = CURRENT_TIMESTAMP WHERE username = %s", (_json(next_permissions), username))
    return get_user_by_username(username)


def get_anchor_profiles(page: int | None = None, page_size: int | None = None, q: str = "") -> dict[str, Any]:
    if not page:
        saved = get_kv("anchor-profiles", None)
        if saved is not None:
            return saved
    page, page_size = paginate(page or 1, page_size or 100)
    where = ""
    args: tuple[Any, ...] = ()
    if q:
        where = "WHERE anchor_name LIKE %s"
        args = (f"%{q}%",)
    total = db.fetch_one(f"SELECT COUNT(*) AS count FROM finvue_anchor_profiles {where}", args)["count"]
    rows = db.fetch_all(
        f"SELECT raw FROM finvue_anchor_profiles {where} ORDER BY updated_at DESC, created_at DESC LIMIT %s OFFSET %s",
        (*args, page_size, (page - 1) * page_size),
    )
    return {"profiles": [parse_json(row["raw"], {}) for row in rows], "total": total, "page": page, "pageSize": page_size}


def save_anchor_profiles(payload: dict[str, Any]) -> dict[str, Any]:
    profiles = safe_array(payload.get("profiles"))
    with db.cursor() as cur:
        cur.execute("DELETE FROM finvue_anchor_profiles")
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            anchor_id = text(profile.get("id") or profile.get("anchorId") or profile.get("anchorName") or profile.get("name")) or _id("anchor")
            anchor_name = text(profile.get("anchorName") or profile.get("name") or anchor_id) or "未命名主播"
            raw = {**profile, "id": anchor_id, "anchorName": anchor_name}
            cur.execute(
                """
                INSERT INTO finvue_anchor_profiles (id, anchor_name, raw, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE anchor_name = VALUES(anchor_name), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                """,
                (anchor_id, anchor_name, _json(raw)),
            )
    return set_kv("anchor-profiles", {"profiles": profiles, "updatedAt": datetime.now(timezone.utc).isoformat()})


def get_anchor_roi_settings() -> dict[str, Any]:
    return get_kv("anchor-roi-settings", {"items": {}})


def save_anchor_roi_settings(payload: dict[str, Any]) -> dict[str, Any]:
    return set_kv("anchor-roi-settings", {"items": safe_object(payload.get("items")), "updatedAt": datetime.now(timezone.utc).isoformat()})


def _library_get(key: str, table: str, item_key: str, page: int | None = None, page_size: int | None = None, q: str = "") -> dict[str, Any]:
    page, page_size = paginate(page or 1, page_size or 100)
    where = ""
    args: tuple[Any, ...] = ()
    if q:
        where = "WHERE raw LIKE %s"
        args = (f"%{q}%",)
    total = db.fetch_one(f"SELECT COUNT(*) AS count FROM {table} {where}", args)["count"]
    rows = db.fetch_all(
        f"SELECT raw FROM {table} {where} ORDER BY updated_at DESC, created_at DESC LIMIT %s OFFSET %s",
        (*args, page_size, (page - 1) * page_size),
    )
    return {item_key: [parse_json(row["raw"], {}) for row in rows], "total": total, "page": page, "pageSize": page_size}


def get_compliance_library(page: int | None = None, page_size: int | None = None, q: str = "") -> dict[str, Any]:
    return _library_get("compliance-library", "finvue_compliance_entries", "entries", page, page_size, q)


def save_compliance_library(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("entry"), dict):
        entry = append_compliance_entries([payload["entry"]])[0]
        current = get_compliance_library()
        return {**current, "entry": entry, "updatedAt": datetime.now(timezone.utc).isoformat()}

    entries = safe_array(payload.get("entries"))
    with db.cursor() as cur:
        cur.execute("DELETE FROM finvue_compliance_entries")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = text(entry.get("id")) or _id("compliance")
            raw = {**entry, "id": entry_id}
            cur.execute(
                """
                INSERT INTO finvue_compliance_entries (id, level, title, phrase, context, suggestion, raw, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE level = VALUES(level), title = VALUES(title), phrase = VALUES(phrase),
                  context = VALUES(context), suggestion = VALUES(suggestion), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                """,
                (
                    entry_id,
                    text(entry.get("level") or entry.get("riskLevel") or entry.get("zone")),
                    text(entry.get("title") or entry.get("phrase") or entry.get("original")),
                    text(entry.get("phrase") or entry.get("original") or entry.get("text")),
                    text(entry.get("context") or entry.get("contextText") or entry.get("originalContext")),
                    text(entry.get("suggestion") or entry.get("rewrite") or entry.get("safeExample")),
                    _json(raw),
                ),
            )
    return set_kv("compliance-library", {"entries": entries, "updatedAt": datetime.now(timezone.utc).isoformat()})


def append_compliance_entries(entries: list[Any]) -> list[dict[str, Any]]:
    saved: list[dict[str, Any]] = []
    with db.cursor() as cur:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = text(entry.get("id")) or _id("compliance")
            raw = {**entry, "id": entry_id}
            cur.execute(
                """
                INSERT INTO finvue_compliance_entries (id, level, title, phrase, context, suggestion, raw, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE level = VALUES(level), title = VALUES(title), phrase = VALUES(phrase),
                  context = VALUES(context), suggestion = VALUES(suggestion), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                """,
                (
                    entry_id,
                    text(entry.get("level") or entry.get("riskLevel") or entry.get("zone")),
                    text(entry.get("title") or entry.get("phrase") or entry.get("original")),
                    text(entry.get("phrase") or entry.get("original") or entry.get("text")),
                    text(entry.get("context") or entry.get("contextText") or entry.get("originalContext")),
                    text(entry.get("suggestion") or entry.get("rewrite") or entry.get("safeExample")),
                    _json(raw),
                ),
            )
            saved.append(raw)
    return saved


def get_case_library(page: int | None = None, page_size: int | None = None, q: str = "") -> dict[str, Any]:
    return _library_get("case-library", "finvue_case_entries", "entries", page, page_size, q)


def save_case_library(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("entry"), dict):
        entry = append_case_entries([payload["entry"]])[0]
        current = get_case_library()
        return {**current, "entry": entry, "updatedAt": datetime.now(timezone.utc).isoformat()}

    entries = safe_array(payload.get("entries"))
    with db.cursor() as cur:
        cur.execute("DELETE FROM finvue_case_entries")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = text(entry.get("id")) or _id("case")
            raw = {**entry, "id": entry_id}
            cur.execute(
                """
                INSERT INTO finvue_case_entries (id, category, title, phrase, context, raw, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE category = VALUES(category), title = VALUES(title), phrase = VALUES(phrase),
                  context = VALUES(context), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                """,
                (entry_id, text(entry.get("category") or entry.get("type")), text(entry.get("title") or entry.get("phrase")), text(entry.get("phrase") or entry.get("text")), text(entry.get("context") or entry.get("originalContext")), _json(raw)),
            )
    return set_kv("case-library", {"entries": entries, "updatedAt": datetime.now(timezone.utc).isoformat()})


def append_case_entries(entries: list[Any]) -> list[dict[str, Any]]:
    saved: list[dict[str, Any]] = []
    with db.cursor() as cur:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = text(entry.get("id")) or _id("case")
            raw = {**entry, "id": entry_id}
            cur.execute(
                """
                INSERT INTO finvue_case_entries (id, category, title, phrase, context, raw, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE category = VALUES(category), title = VALUES(title), phrase = VALUES(phrase),
                  context = VALUES(context), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                """,
                (
                    entry_id,
                    text(entry.get("category") or entry.get("type")),
                    text(entry.get("title") or entry.get("phrase")),
                    text(entry.get("phrase") or entry.get("quote") or entry.get("text")),
                    text(entry.get("context") or entry.get("originalContext")),
                    _json(raw),
                ),
            )
            saved.append(raw)
    return saved


def get_transcript_library(page: int | None = None, page_size: int | None = None, q: str = "") -> dict[str, Any]:
    page, page_size = paginate(page or 1, page_size or 100)
    where = ""
    args: tuple[Any, ...] = ()
    if q:
        where = "WHERE anchor_name LIKE %s OR title LIKE %s OR content LIKE %s OR raw LIKE %s"
        args = (f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%")
    total = db.fetch_one(f"SELECT COUNT(*) AS count FROM finvue_transcripts {where}", args)["count"]
    rows = db.fetch_all(
        f"SELECT raw FROM finvue_transcripts {where} ORDER BY updated_at DESC, created_at DESC LIMIT %s OFFSET %s",
        (*args, page_size, (page - 1) * page_size),
    )
    entries = [parse_json(row["raw"], {}) for row in rows]
    return {"entries": entries, "items": entries, "total": total, "page": page, "pageSize": page_size}


def save_transcript_library(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("entry"), dict):
        entry = append_transcript_entry(payload["entry"])
        current = get_transcript_library()
        return {**current, "entry": entry, "updatedAt": datetime.now(timezone.utc).isoformat()}

    items = safe_array(payload.get("entries") or payload.get("items") or payload.get("transcripts"))
    with db.cursor() as cur:
        cur.execute("DELETE FROM finvue_transcripts")
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = text(item.get("id")) or _id("transcript")
            anchor_name = text(item.get("anchorName") or item.get("anchor") or item.get("name"))
            title = text(item.get("title") or item.get("fileName"))
            content = text(item.get("content") or item.get("text") or item.get("transcript"))
            raw = {**item, "id": item_id}
            cur.execute(
                """
                INSERT INTO finvue_transcripts (id, anchor_name, title, content, raw, updated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE anchor_name = VALUES(anchor_name), title = VALUES(title),
                  content = VALUES(content), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                """,
                (item_id, anchor_name or None, title or None, content or None, _json(raw)),
            )
    payload_out = {"entries": items, "items": items, "updatedAt": datetime.now(timezone.utc).isoformat()}
    set_kv("transcript-library", payload_out)
    return payload_out


def append_transcript_entry(item: dict[str, Any]) -> dict[str, Any]:
    item_id = text(item.get("id")) or _id("transcript")
    anchor_name = text(item.get("anchorName") or item.get("anchor") or item.get("name"))
    title = text(item.get("title") or item.get("fileName"))
    content = text(item.get("content") or item.get("text") or item.get("transcript"))
    raw = {**item, "id": item_id, "anchorName": anchor_name, "title": title, "content": content}
    db.execute(
        """
        INSERT INTO finvue_transcripts (id, anchor_name, title, content, raw, updated_at)
        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON DUPLICATE KEY UPDATE anchor_name = VALUES(anchor_name), title = VALUES(title),
          content = VALUES(content), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
        """,
        (item_id, anchor_name or None, title or None, content or None, _json(raw)),
    )
    return raw


def delete_transcript(item_id: str) -> dict[str, Any]:
    db.execute("DELETE FROM finvue_transcripts WHERE id = %s", (item_id,))
    current = get_transcript_library()
    set_kv("transcript-library", {"entries": current["entries"], "items": current["entries"], "updatedAt": datetime.now(timezone.utc).isoformat()})
    return current


def delete_transcripts_by_anchor(anchor_name: str) -> dict[str, Any]:
    db.execute("DELETE FROM finvue_transcripts WHERE anchor_name = %s", (anchor_name,))
    current = get_transcript_library()
    set_kv("transcript-library", {"entries": current["entries"], "items": current["entries"], "updatedAt": datetime.now(timezone.utc).isoformat()})
    return current


def get_reports(page: int = 1, page_size: int = 20, q: str = "", anchor_name: str = "") -> dict[str, Any]:
    page, page_size = paginate(page, page_size)
    clauses: list[str] = []
    args: list[Any] = []
    if q:
        clauses.append("(title LIKE %s OR summary LIKE %s OR markdown LIKE %s)")
        args.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    if anchor_name:
        clauses.append("anchor_name = %s")
        args.append(anchor_name)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = db.fetch_one(f"SELECT COUNT(*) AS count FROM finvue_analysis_reports {where}", tuple(args))["count"]
    rows = db.fetch_all(
        f"SELECT raw FROM finvue_analysis_reports {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (*args, page_size, (page - 1) * page_size),
    )
    return {"reports": [parse_json(row["raw"], {}) for row in rows], "total": total, "page": page, "pageSize": page_size}


def save_report(payload: dict[str, Any]) -> dict[str, Any]:
    report_id = text(payload.get("id")) or _id("report")
    anchor_name = text(payload.get("anchorName") or payload.get("anchor"))
    title = text(payload.get("title") or payload.get("reportTitle") or "分析报告")
    markdown = text(payload.get("markdown") or payload.get("content"))
    html = text(payload.get("html"))
    summary = text(payload.get("summary") or payload.get("conclusion"))
    raw = {**payload, "id": report_id, "anchorName": anchor_name, "title": title}
    db.execute(
        """
        INSERT INTO finvue_analysis_reports (id, anchor_name, report_type, title, markdown, html, summary, raw, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON DUPLICATE KEY UPDATE anchor_name = VALUES(anchor_name), report_type = VALUES(report_type),
          title = VALUES(title), markdown = VALUES(markdown), html = VALUES(html), summary = VALUES(summary),
          raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
        """,
        (report_id, anchor_name or None, text(payload.get("reportType") or payload.get("type")) or None, title, markdown or None, html or None, summary or None, _json(raw)),
    )
    return raw


def upsert_anchor_profiles(profiles: list[Any]) -> int:
    saved = 0
    with db.cursor() as cur:
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            anchor_id = text(profile.get("id") or profile.get("anchorId") or profile.get("anchorName") or profile.get("name")) or _id("anchor")
            anchor_name = text(profile.get("anchorName") or profile.get("name") or anchor_id) or "未命名主播"
            existing = None
            cur.execute("SELECT raw FROM finvue_anchor_profiles WHERE id = %s OR anchor_name = %s ORDER BY updated_at DESC LIMIT 1", (anchor_id, anchor_name))
            row = cur.fetchone()
            if row:
                existing = parse_json(row.get("raw"), {})
            raw = {**safe_object(existing), **profile, "id": anchor_id, "anchorName": anchor_name}
            old_snapshots = safe_array(safe_object(existing).get("snapshots") if existing else [])
            next_snapshots = safe_array(profile.get("snapshots"))
            if old_snapshots or next_snapshots:
                by_id: dict[str, Any] = {}
                for item in old_snapshots + next_snapshots:
                    if not isinstance(item, dict):
                        continue
                    key = text(item.get("id") or item.get("analyzedAt") or len(by_id))
                    by_id[key] = item
                raw["snapshots"] = sorted(by_id.values(), key=lambda item: str(item.get("analyzedAt") or item.get("createdAt") or ""), reverse=True)
            cur.execute(
                """
                INSERT INTO finvue_anchor_profiles (id, anchor_name, raw, updated_at)
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE anchor_name = VALUES(anchor_name), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                """,
                (anchor_id, anchor_name, _json(raw)),
            )
            saved += 1
    return saved


def get_customer_library(page: int | None = None, page_size: int | None = None, q: str = "", mode: str = "") -> dict[str, Any]:
    if mode == "anchors":
        rows = db.fetch_all(
            """
            SELECT COALESCE(latest_anchor_name, '未命名主播') AS anchorName,
                   COUNT(*) AS customerCount,
                   SUM(COALESCE(session_count, 0)) AS sessionCount,
                   MAX(latest_analyzed_at) AS latestAt
            FROM (
              SELECT p.customer_id, p.latest_anchor_name, p.latest_analyzed_at, COUNT(s.session_id) AS session_count
              FROM finvue_customer_profiles p
              LEFT JOIN finvue_customer_sessions s ON s.customer_id = p.customer_id
              GROUP BY p.customer_id, p.latest_anchor_name, p.latest_analyzed_at
            ) t
            GROUP BY COALESCE(latest_anchor_name, '未命名主播')
            ORDER BY latestAt DESC, customerCount DESC
            """
        )
        anchor_groups = []
        for r in rows:
            anchor_name = r["anchorName"]
            top_rows = db.fetch_all(
                """
                SELECT customer_id, customer_name, latest_anchor_name, latest_analyzed_at, latest_live_theme,
                       latest_rank, best_rank, avg_watch_seconds, labels, tags
                FROM finvue_customer_profiles
                WHERE COALESCE(latest_anchor_name, '未命名主播') = %s
                ORDER BY COALESCE(best_rank, 999999) ASC, latest_analyzed_at DESC, updated_at DESC
                LIMIT 12
                """,
                (anchor_name,),
            )
            customers = []
            segment_counts: dict[str, int] = {}
            for item in top_rows:
                labels = safe_array(parse_json(item.get("labels"), []))
                tags = safe_array(parse_json(item.get("tags"), []))
                customer = {
                    "id": item.get("customer_id"),
                    "customerId": item.get("customer_id"),
                    "name": item.get("customer_name"),
                    "customerName": item.get("customer_name"),
                    "latestAnchorName": item.get("latest_anchor_name") or anchor_name,
                    "latestAnalyzedAt": iso(item.get("latest_analyzed_at")),
                    "latestLiveTheme": item.get("latest_live_theme") or "",
                    "latestRank": to_int(item.get("latest_rank")),
                    "bestRank": to_int(item.get("best_rank")),
                    "avgWatchSeconds": to_int(item.get("avg_watch_seconds")),
                    "labels": labels,
                    "tags": tags,
                    "sessions": [],
                }
                customers.append(customer)
                for label in labels + tags:
                    label_text = text(label)
                    if label_text:
                        segment_counts[label_text] = segment_counts.get(label_text, 0) + 1
            anchor_groups.append(
                {
                    "anchorName": anchor_name,
                    "uniqueCustomerCount": int(r["customerCount"] or 0),
                    "customerCount": int(r["customerCount"] or 0),
                    "totalSessions": int(r["sessionCount"] or 0),
                    "sessionCount": int(r["sessionCount"] or 0),
                    "latestAnalyzedAt": iso(r.get("latestAt")),
                    "latestAt": iso(r.get("latestAt")),
                    "bestRank": min([to_int(c.get("bestRank")) for c in customers if to_int(c.get("bestRank"))] or [0]),
                    "segmentCounts": segment_counts,
                    "customers": customers,
                }
            )
        stats = {
            "anchorCount": len(anchor_groups),
            "customerCount": sum(int(item.get("uniqueCustomerCount") or 0) for item in anchor_groups),
            "sessionCount": sum(int(item.get("totalSessions") or 0) for item in anchor_groups),
            "latestAnalyzedAt": anchor_groups[0]["latestAnalyzedAt"] if anchor_groups else "",
        }
        return {"customers": [], "anchorGroups": anchor_groups, "anchors": anchor_groups, "stats": stats}

    if mode == "compact":
        rows = db.fetch_all(
            """
            SELECT raw FROM finvue_customer_profiles
            ORDER BY latest_analyzed_at DESC, updated_at DESC
            LIMIT 10000
            """
        )
        customers = [parse_json(row["raw"], {}) for row in rows]
        return {"customers": customers, "total": len(customers), "page": 1, "pageSize": len(customers)}

    page, page_size = paginate(page or 1, page_size or 20)
    where = ""
    args: tuple[Any, ...] = ()
    if q:
        where = "WHERE customer_name LIKE %s OR latest_anchor_name LIKE %s OR raw LIKE %s"
        args = (f"%{q}%", f"%{q}%", f"%{q}%")
    total = db.fetch_one(f"SELECT COUNT(*) AS count FROM finvue_customer_profiles {where}", args)["count"]
    rows = db.fetch_all(
        f"SELECT raw FROM finvue_customer_profiles {where} ORDER BY latest_analyzed_at DESC, updated_at DESC LIMIT %s OFFSET %s",
        (*args, page_size, (page - 1) * page_size),
    )
    return {"customers": [parse_json(row["raw"], {}) for row in rows], "total": total, "page": page, "pageSize": page_size}


def _customer_latest_session(customer: dict[str, Any]) -> dict[str, Any]:
    sessions = [item for item in safe_array(customer.get("sessions") or customer.get("records") or customer.get("history")) if isinstance(item, dict)]
    return sorted(sessions, key=lambda item: str(item.get("analyzedAt") or item.get("createdAt") or ""), reverse=True)[0] if sessions else {}


def upsert_customer_entries(customers: list[Any]) -> dict[str, int]:
    saved_customers = 0
    saved_sessions = 0
    with db.cursor() as cur:
        for customer in customers:
            if not isinstance(customer, dict):
                continue
            customer_id = text(customer.get("id") or customer.get("customerId") or customer.get("name") or customer.get("customerName")) or _id("customer")
            customer_name = text(customer.get("name") or customer.get("customerName") or customer_id) or "未命名客户"
            sessions = [item for item in safe_array(customer.get("sessions") or customer.get("records") or customer.get("history")) if isinstance(item, dict)]
            latest_session = _customer_latest_session({**customer, "sessions": sessions})
            existing = None
            cur.execute("SELECT raw FROM finvue_customer_profiles WHERE customer_id = %s", (customer_id,))
            row = cur.fetchone()
            if row:
                existing = parse_json(row.get("raw"), {})
            old_sessions = safe_array(safe_object(existing).get("sessions") if existing else [])
            by_session: dict[str, dict[str, Any]] = {}
            for idx, session in enumerate(old_sessions + sessions):
                if not isinstance(session, dict):
                    continue
                sid = text(session.get("id") or session.get("sessionId")) or f"{customer_id}-{idx}"
                by_session[sid] = {**session, "sessionId": sid}
            merged_sessions = sorted(by_session.values(), key=lambda item: str(item.get("analyzedAt") or item.get("createdAt") or ""), reverse=True)
            raw = {**safe_object(existing), **customer, "id": customer_id, "customerId": customer_id, "name": customer_name, "customerName": customer_name, "sessions": merged_sessions}
            latest_session = _customer_latest_session(raw)
            labels = safe_array(raw.get("labels")) + safe_array(latest_session.get("labels"))
            tags = safe_array(raw.get("tags")) + safe_array(latest_session.get("tags"))
            best_rank = raw.get("bestRank") or min([to_int(s.get("watchRank")) for s in merged_sessions if to_int(s.get("watchRank"))] or [0])
            cur.execute(
                """
                INSERT INTO finvue_customer_profiles
                  (customer_id, customer_name, latest_anchor_name, latest_analyzed_at, latest_live_theme,
                   latest_rank, best_rank, avg_watch_seconds, labels, tags, raw, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE customer_name = VALUES(customer_name), latest_anchor_name = VALUES(latest_anchor_name),
                  latest_analyzed_at = VALUES(latest_analyzed_at), latest_live_theme = VALUES(latest_live_theme),
                  latest_rank = VALUES(latest_rank), best_rank = VALUES(best_rank), avg_watch_seconds = VALUES(avg_watch_seconds),
                  labels = VALUES(labels), tags = VALUES(tags), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                """,
                (
                    customer_id,
                    customer_name,
                    text(raw.get("anchorName") or raw.get("latestAnchorName") or latest_session.get("anchorName")) or None,
                    _dt(raw.get("latestAnalyzedAt") or latest_session.get("analyzedAt") or latest_session.get("createdAt")),
                    text(raw.get("liveTheme") or raw.get("latestLiveTheme") or latest_session.get("liveTheme") or latest_session.get("title")) or None,
                    raw.get("latestRank") or latest_session.get("rank") or latest_session.get("watchRank"),
                    best_rank,
                    raw.get("avgWatchSeconds") or latest_session.get("watchDurationSeconds"),
                    _json(list(dict.fromkeys([text(item) for item in labels if text(item)]))),
                    _json(list(dict.fromkeys([text(item) for item in tags if text(item)]))),
                    _json(raw),
                ),
            )
            saved_customers += 1
            for idx, session in enumerate(merged_sessions):
                session_id = text(session.get("id") or session.get("sessionId")) or f"{customer_id}-{idx}"
                cur.execute(
                    """
                    INSERT INTO finvue_customer_sessions
                      (session_id, customer_id, anchor_name, room_id, live_theme, report_type, metric_type,
                       metric_value, watch_rank, watch_duration_seconds, analyzed_at, source_file, raw, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE anchor_name = VALUES(anchor_name), room_id = VALUES(room_id),
                      live_theme = VALUES(live_theme), report_type = VALUES(report_type), metric_type = VALUES(metric_type),
                      metric_value = VALUES(metric_value), watch_rank = VALUES(watch_rank),
                      watch_duration_seconds = VALUES(watch_duration_seconds), analyzed_at = VALUES(analyzed_at),
                      source_file = VALUES(source_file), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        session_id,
                        customer_id,
                        text(session.get("anchorName") or raw.get("anchorName") or raw.get("latestAnchorName")) or None,
                        text(session.get("roomId") or session.get("room_id")) or None,
                        text(session.get("liveTheme") or session.get("title")) or None,
                        text(session.get("reportType")) or None,
                        text(session.get("metricType")) or None,
                        text(session.get("metricValue")) or None,
                        session.get("rank") or session.get("watchRank"),
                        session.get("watchSeconds") or session.get("watchDurationSeconds"),
                        _dt(session.get("analyzedAt") or session.get("createdAt")),
                        text(session.get("sourceFile")) or None,
                        _json(session),
                    ),
                )
                saved_sessions += 1
    return {"customers": saved_customers, "sessions": saved_sessions}


def save_customer_library(payload: dict[str, Any]) -> dict[str, Any]:
    entries = safe_array(payload.get("entries"))
    if entries:
        normalized_customers = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            customer_name = text(entry.get("customerName") or entry.get("name") or entry.get("customerId") or entry.get("id"))
            customer_id = text(entry.get("customerId") or entry.get("id") or customer_name) or _id("customer")
            session_id = text(entry.get("sessionId") or entry.get("id")) or f"{customer_id}-{text(entry.get('analyzedAt')) or _id('session')}"
            normalized_customers.append(
                {
                    "id": customer_id,
                    "customerId": customer_id,
                    "name": customer_name or customer_id,
                    "customerName": customer_name or customer_id,
                    "anchorName": text(entry.get("anchorName")),
                    "latestLiveTheme": text(entry.get("liveTheme")),
                    "labels": safe_array(entry.get("labels")),
                    "tags": safe_array(entry.get("tags")),
                    "sessions": [{**entry, "id": session_id, "sessionId": session_id}],
                }
            )
        stats = upsert_customer_entries(normalized_customers)
        current = get_customer_library(mode="compact")
        return {**current, "saved": stats, "updatedAt": datetime.now(timezone.utc).isoformat()}

    customers = safe_array(payload.get("customers"))
    with db.cursor() as cur:
        cur.execute("DELETE FROM finvue_customer_sessions")
        cur.execute("DELETE FROM finvue_customer_profiles")
        for customer in customers:
            if not isinstance(customer, dict):
                continue
            customer_id = text(customer.get("id") or customer.get("customerId") or customer.get("name") or customer.get("customerName")) or _id("customer")
            customer_name = text(customer.get("name") or customer.get("customerName") or customer_id) or "未命名客户"
            sessions = safe_array(customer.get("sessions") or customer.get("records") or customer.get("history"))
            latest_session = sessions[0] if sessions else {}
            raw = {**customer, "id": customer_id, "name": customer_name}
            cur.execute(
                """
                INSERT INTO finvue_customer_profiles
                  (customer_id, customer_name, latest_anchor_name, latest_analyzed_at, latest_live_theme,
                   latest_rank, best_rank, avg_watch_seconds, labels, tags, raw, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON DUPLICATE KEY UPDATE customer_name = VALUES(customer_name), latest_anchor_name = VALUES(latest_anchor_name),
                  latest_analyzed_at = VALUES(latest_analyzed_at), latest_live_theme = VALUES(latest_live_theme),
                  latest_rank = VALUES(latest_rank), best_rank = VALUES(best_rank), avg_watch_seconds = VALUES(avg_watch_seconds),
                  labels = VALUES(labels), tags = VALUES(tags), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                """,
                (
                    customer_id,
                    customer_name,
                    text(customer.get("anchorName") or latest_session.get("anchorName")) or None,
                    _dt(customer.get("latestAt") or latest_session.get("analyzedAt") or latest_session.get("createdAt")),
                    text(customer.get("liveTheme") or latest_session.get("liveTheme") or latest_session.get("title")) or None,
                    customer.get("latestRank") or latest_session.get("rank"),
                    customer.get("bestRank"),
                    customer.get("avgWatchSeconds"),
                    _json(customer.get("labels") or []),
                    _json(customer.get("tags") or []),
                    _json(raw),
                ),
            )
            for idx, session in enumerate(sessions):
                if not isinstance(session, dict):
                    continue
                session_id = text(session.get("id") or session.get("sessionId")) or f"{customer_id}-{idx}"
                cur.execute(
                    """
                    INSERT INTO finvue_customer_sessions
                      (session_id, customer_id, anchor_name, room_id, live_theme, report_type, metric_type,
                       metric_value, watch_rank, watch_duration_seconds, analyzed_at, source_file, raw, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON DUPLICATE KEY UPDATE anchor_name = VALUES(anchor_name), room_id = VALUES(room_id),
                      live_theme = VALUES(live_theme), report_type = VALUES(report_type), metric_type = VALUES(metric_type),
                      metric_value = VALUES(metric_value), watch_rank = VALUES(watch_rank),
                      watch_duration_seconds = VALUES(watch_duration_seconds), analyzed_at = VALUES(analyzed_at),
                      source_file = VALUES(source_file), raw = VALUES(raw), updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        session_id,
                        customer_id,
                        text(session.get("anchorName") or customer.get("anchorName")) or None,
                        text(session.get("roomId") or session.get("room_id")) or None,
                        text(session.get("liveTheme") or session.get("title")) or None,
                        text(session.get("reportType")) or None,
                        text(session.get("metricType")) or None,
                        text(session.get("metricValue")) or None,
                        session.get("rank") or session.get("watchRank"),
                        session.get("watchSeconds") or session.get("watchDurationSeconds"),
                        _dt(session.get("analyzedAt") or session.get("createdAt")),
                        text(session.get("sourceFile")) or None,
                        _json(session),
                    ),
                )
    return set_kv("customer-library", {"customers": customers, "updatedAt": datetime.now(timezone.utc).isoformat()})


def persist_analysis_bundle(payload: dict[str, Any], created_by: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "report": None,
        "transcriptEntry": None,
        "anchorProfiles": 0,
        "customerStats": {"customers": 0, "sessions": 0},
        "complianceEntries": [],
        "caseEntries": [],
    }
    if isinstance(payload.get("report"), dict):
        report = {**payload["report"]}
        if created_by and not report.get("createdBy"):
            report["createdBy"] = created_by
        result["report"] = save_report(report)

    transcript_entry = payload.get("transcriptEntry")
    if isinstance(transcript_entry, dict):
        result["transcriptEntry"] = append_transcript_entry(transcript_entry)

    anchor_profile = payload.get("anchorProfile")
    if isinstance(anchor_profile, dict) and text(anchor_profile.get("anchorName") or anchor_profile.get("name")):
        result["anchorProfiles"] = upsert_anchor_profiles([anchor_profile])

    customer_entries = safe_array(payload.get("customerEntries"))
    if customer_entries:
        normalized = []
        for entry in customer_entries:
            if not isinstance(entry, dict):
                continue
            customer_name = text(entry.get("customerName") or entry.get("name") or entry.get("customerId") or entry.get("id"))
            customer_id = text(entry.get("customerId") or entry.get("id") or customer_name) or _id("customer")
            session_id = text(entry.get("sessionId") or entry.get("id")) or f"{customer_id}-{text(entry.get('analyzedAt')) or _id('session')}"
            normalized.append(
                {
                    "id": customer_id,
                    "customerId": customer_id,
                    "name": customer_name or customer_id,
                    "customerName": customer_name or customer_id,
                    "anchorName": text(entry.get("anchorName")),
                    "latestLiveTheme": text(entry.get("liveTheme")),
                    "labels": safe_array(entry.get("labels")),
                    "tags": safe_array(entry.get("tags")),
                    "sessions": [{**entry, "id": session_id, "sessionId": session_id}],
                }
            )
        result["customerStats"] = upsert_customer_entries(normalized)

    compliance_entries = append_compliance_entries(safe_array(payload.get("complianceEntries")))
    case_entries = append_case_entries(safe_array(payload.get("caseEntries")))
    result["complianceEntries"] = compliance_entries
    result["caseEntries"] = case_entries
    return result


def get_customer_trends_summary(anchor_name: str = "") -> dict[str, Any]:
    where = ""
    args: tuple[Any, ...] = ()
    if anchor_name:
        where = "WHERE anchor_name = %s"
        args = (anchor_name,)
    rows = db.fetch_all(
        f"""
        SELECT DATE_FORMAT(analyzed_at, '%%Y-%%m') AS month,
               COUNT(DISTINCT customer_id) AS customers,
               COUNT(*) AS sessions,
               AVG(watch_duration_seconds) AS avgWatchSeconds
        FROM finvue_customer_sessions
        {where}
        GROUP BY DATE_FORMAT(analyzed_at, '%%Y-%%m')
        ORDER BY month ASC
        """,
        args,
    )
    return {"months": [{"month": r["month"], "customers": int(r["customers"] or 0), "sessions": int(r["sessions"] or 0), "avgWatchSeconds": int(r["avgWatchSeconds"] or 0)} for r in rows]}


def enqueue_job(job_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    job_id = _id("job")
    db.execute(
        "INSERT INTO finvue_jobs (id, type, status, progress, payload) VALUES (%s, %s, 'queued', 0, %s)",
        (job_id, job_type, _json(payload or {})),
    )
    return get_job(job_id) or {"id": job_id, "type": job_type, "status": "queued", "progress": 0}


def get_job(job_id: str) -> dict[str, Any] | None:
    row = db.fetch_one("SELECT * FROM finvue_jobs WHERE id = %s", (job_id,))
    if not row:
        return None
    result = parse_json(row.get("result"), None)
    result_obj = result if isinstance(result, dict) else {}
    status = row["status"]
    public_status = "completed" if status == "success" else status
    return {
        "id": row["id"],
        "type": row["type"],
        "status": public_status,
        "rawStatus": status,
        "progress": int(row.get("progress") or 0),
        "payload": parse_json(row.get("payload"), {}),
        "result": result,
        "phase": result_obj.get("phase"),
        "message": result_obj.get("message"),
        "meta": result_obj.get("meta"),
        "error": row.get("error"),
        "attempts": int(row.get("attempts") or 0),
        "createdAt": iso(row.get("created_at")),
        "startedAt": iso(row.get("started_at")),
        "finishedAt": iso(row.get("finished_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


def list_jobs(page: int = 1, page_size: int = 20, status: str = "") -> dict[str, Any]:
    page, page_size = paginate(page, page_size)
    where = ""
    args: tuple[Any, ...] = ()
    if status:
        where = "WHERE status = %s"
        args = (status,)
    total = db.fetch_one(f"SELECT COUNT(*) AS count FROM finvue_jobs {where}", args)["count"]
    rows = db.fetch_all(
        f"SELECT id FROM finvue_jobs {where} ORDER BY created_at DESC LIMIT %s OFFSET %s",
        (*args, page_size, (page - 1) * page_size),
    )
    return {"jobs": [get_job(row["id"]) for row in rows], "total": total, "page": page, "pageSize": page_size}


def update_job(job_id: str, **fields: Any) -> None:
    allowed = {"status", "progress", "result", "error", "attempts", "started_at", "finished_at"}
    parts: list[str] = []
    args: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        parts.append(f"{key} = %s")
        args.append(_json(value) if key == "result" else value)
    if not parts:
        return
    args.append(job_id)
    db.execute(f"UPDATE finvue_jobs SET {', '.join(parts)}, updated_at = CURRENT_TIMESTAMP WHERE id = %s", tuple(args))


def retry_job(job_id: str) -> dict[str, Any] | None:
    db.execute(
        "UPDATE finvue_jobs SET status = 'queued', progress = 0, error = NULL, started_at = NULL, finished_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
        (job_id,),
    )
    return get_job(job_id)


def claim_next_job() -> dict[str, Any] | None:
    job_id = ""
    with db.cursor() as cur:
        cur.execute("SELECT id FROM finvue_jobs WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1 FOR UPDATE")
        row = cur.fetchone()
        if not row:
            return None
        job_id = row["id"]
        cur.execute(
            "UPDATE finvue_jobs SET status = 'running', attempts = attempts + 1, started_at = CURRENT_TIMESTAMP, progress = 5, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (job_id,),
        )
    return get_job(job_id)
