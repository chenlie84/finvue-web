from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import config
import security
from services import object_storage


router = APIRouter()


@router.post("/api/upload-source")
async def upload_source_file(file: UploadFile = File(...), _: dict = Depends(security.require_permission("live"))) -> dict:
    data = await file.read()
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"文件超过限制：{config.MAX_UPLOAD_BYTES} bytes")
    try:
        result = object_storage.upload_bytes(
            data,
            file_name=file.filename or "source-file",
            prefix=config.SOURCE_CEPH_KEY_PREFIX,
            content_type=file.content_type or None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True, "file": result}
