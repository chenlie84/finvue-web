from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

import db
import migrate
import security
import store


router = APIRouter()


@router.get("/api/admin/users")
def users(_: dict = Depends(security.require_admin)) -> dict:
    return {"users": [security.sanitize_user(user) for user in store.list_users()]}


@router.patch("/api/admin/users/role")
async def update_role(request: Request, _: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    username = security.normalize_username(body.get("username"))
    role = store.text(body.get("role"))
    if role not in {"admin", "user"}:
        raise HTTPException(status_code=400, detail="角色只能是 admin 或 user")
    user = store.update_user_role(username, role)
    if not user:
        raise HTTPException(status_code=404, detail="未找到用户")
    return {"ok": True, "user": security.sanitize_user(user)}


@router.patch("/api/admin/users/permissions")
async def update_permissions(request: Request, _: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    username = security.normalize_username(body.get("username"))
    user = store.update_user_permissions(username, body.get("permissions"))
    if not user:
        raise HTTPException(status_code=404, detail="未找到用户")
    return {"ok": True, "user": security.sanitize_user(user)}


@router.post("/api/admin/migrations/reset")
async def reset_migration(request: Request, _: dict = Depends(security.require_admin)) -> dict:
    """删除迁移记录并重新执行（用于修复失败的迁移）"""
    body = await request.json()
    filename = body.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="需要提供 filename")
    
    # 删除迁移记录
    db.execute("DELETE FROM finvue_schema_migrations WHERE filename = %s", (filename,))
    
    # 重新执行迁移
    ran = migrate.run_migrations()
    return {"ok": True, "ran": ran}


@router.post("/api/admin/migrations/run")
def run_migrations(_: dict = Depends(security.require_admin)) -> dict:
    """手动运行迁移"""
    ran = migrate.run_migrations()
    return {"ok": True, "ran": ran}
