from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

import ai_router
import config
import security
import store
from services import pdf_export
from services import object_storage


router = APIRouter()


@router.post("/api/generate")
async def generate(request: Request, session: dict = Depends(security.require_permission("live"))) -> dict:
    body = await request.json()
    return ai_router.generate(body, username=session.get("username"))


@router.post("/api/generate-stream")
async def generate_stream(request: Request, session: dict = Depends(security.require_permission("live"))) -> StreamingResponse:
    body = await request.json()

    def events():
        yield json.dumps({"type": "status", "message": "已接收任务，正在调用 AI 路由"}, ensure_ascii=False) + "\n"
        try:
            result = ai_router.generate(body, username=session.get("username"))
            markdown = result.get("markdown") or ""
            for index in range(0, len(markdown), 1200):
                yield json.dumps({"type": "chunk", "content": markdown[index : index + 1200]}, ensure_ascii=False) + "\n"
            yield json.dumps({"type": "done", **result}, ensure_ascii=False) + "\n"
        except Exception as exc:
            yield json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson; charset=utf-8")


@router.post("/api/analysis-persist")
async def persist_analysis(request: Request, session: dict = Depends(security.require_permission("live"))) -> dict:
    body = await request.json()
    return store.persist_analysis_bundle(body, created_by=str(session.get("username") or ""))


@router.post("/api/export-plugin")
async def export_plugin(request: Request, _: dict = Depends(security.require_permission("export"))) -> dict:
    body = await request.json()
    return {"ok": True, "content": body}


@router.post("/api/export-report-pdf")
async def export_report_pdf(request: Request, _: dict = Depends(security.require_any_permission("live", "export"))) -> StreamingResponse:
    body = await request.json()
    file_name = pdf_export.safe_pdf_filename(str(body.get("fileName") or body.get("filename") or "finvue-report"))
    try:
        data = pdf_export.render_pdf_bytes(str(body.get("html") or ""))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    headers = {"Content-Disposition": f'attachment; filename="{file_name}.pdf"'}
    if config.has_ceph_config():
        try:
            uploaded = object_storage.upload_bytes(data, file_name=f"{file_name}.pdf", prefix=config.CEPH_KEY_PREFIX, content_type="application/pdf")
            headers["X-FinVue-S3-Key"] = uploaded.get("key", "")
            headers["X-FinVue-S3-Url"] = uploaded.get("url", "")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF 已生成，但上传 S3 失败：{exc}") from exc
    return StreamingResponse(
        iter([data]),
        media_type="application/pdf",
        headers=headers,
    )


@router.post("/api/extract-pdf")
async def extract_pdf(_: Request, __: dict = Depends(security.require_permission("live"))) -> dict:
    return {"ok": False, "error": "服务端 PDF 文本提取未启用；页面会自动尝试浏览器端读取。若仍失败，请上传 txt/docx。"}
