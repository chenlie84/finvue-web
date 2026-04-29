from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

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
