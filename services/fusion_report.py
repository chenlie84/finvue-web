from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Callable

import store


def _section(text: str, heading: str) -> str:
    lines = str(text or "").replace("\r", "").split("\n")
    pattern = re.compile(rf"^#{{1,4}}\s*{re.escape(heading)}\s*$")
    start = next((i for i, line in enumerate(lines) if pattern.match(line.strip())), -1)
    if start < 0:
        return ""
    collected: list[str] = []
    for line in lines[start + 1 :]:
        if re.match(r"^#{1,4}\s+", line.strip()):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def extract_transcript_text(text: str) -> str:
    for heading in ("文字记录", "逐字稿", "直播逐字稿", "转写原文", "原文"):
        value = _section(text, heading)
        if value:
            return value
    return ""


def infer_anchor_name(payload: dict[str, Any], text: str) -> str:
    for key in ("anchorName", "anchor", "name"):
        value = store.text(payload.get(key))
        if value:
            return value
    file_name = store.text(payload.get("fileName") or payload.get("sourceFile"))
    if file_name:
        clean = re.sub(r"\.(txt|md|markdown|pdf|docx)$", "", file_name, flags=re.I)
        clean = re.split(r"[_\-]\d{4}|\d{4}年|\d{4}-\d{2}", clean)[0].strip("_- ")
        if clean:
            return clean[:80]
    match = re.search(r"主播(?:名称|名)?[：:]\s*([^\n#，,]+)", text)
    return match.group(1).strip()[:80] if match else "未命名主播"


def infer_title(payload: dict[str, Any], text: str) -> str:
    for key in ("title", "liveTheme", "reportTitle"):
        value = store.text(payload.get(key))
        if value:
            return value
    match = re.search(r"(?:直播主题|主题|标题)[：:]\s*([^\n#]+)", text)
    if match:
        return match.group(1).strip()[:160]
    first_heading = re.search(r"^#{1,3}\s+(.+)$", text, re.M)
    return first_heading.group(1).strip()[:160] if first_heading else "融合报告解析"


def parse_fusion_report(payload: dict[str, Any], progress: Callable[[int, str, str, dict[str, Any] | None], None] | None = None) -> dict[str, Any]:
    progress = progress or (lambda *_args, **_kwargs: None)
    text = store.text(payload.get("text") or payload.get("content") or payload.get("markdown"))
    if not text:
        raise RuntimeError("融合报告解析失败：缺少文本内容")
    progress(20, "parse", "正在识别融合报告中的主播、主题和逐字稿", None)

    anchor_name = infer_anchor_name(payload, text)
    title = infer_title(payload, text)
    transcript_text = extract_transcript_text(text)
    now = datetime.now(timezone.utc).isoformat()
    source_file = store.text(payload.get("fileName") or payload.get("sourceFile"))

    saved_transcripts = 0
    if transcript_text:
        entry = {
            "id": store.text(payload.get("transcriptId")) or store._id("transcript"),
            "anchorName": anchor_name,
            "title": title,
            "fileName": source_file,
            "content": transcript_text,
            "text": transcript_text,
            "reportType": payload.get("reportType") or "fusionReport",
            "createdAt": now,
            "updatedAt": now,
        }
        store.append_transcript_entry(entry)
        saved_transcripts = 1

    progress(60, "save", "正在保存分析报告", {"anchorName": anchor_name})
    report = store.save_report(
        {
            "id": store.text(payload.get("reportId")) or store._id("report"),
            "anchorName": anchor_name,
            "title": title,
            "reportType": payload.get("reportType") or "fusionReport",
            "markdown": text,
            "summary": text[:240],
            "sourceFile": source_file,
            "createdAt": now,
            "updatedAt": now,
        }
    )
    return {
        "ok": True,
        "message": "融合报告解析完成",
        "phase": "done",
        "anchorName": anchor_name,
        "title": title,
        "transcripts": saved_transcripts,
        "reports": 1,
        "reportId": report.get("id"),
    }
