from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

import config
import security
import store


router = APIRouter()


DEFAULT_REGISTER_PERMISSIONS = {
    "home": True,
    "live": True,
}


@router.get("/api/session")
def session(request: Request) -> dict:
    current = security.get_session(request)
    return {"authenticated": bool(current), "user": current, "registrationEnabled": bool(config.ALLOW_OPEN_REGISTRATION)}


@router.post("/api/login")
async def login(request: Request, response: Response) -> dict:
    body = await request.json()
    username = security.normalize_username(body.get("username"))
    password = str(body.get("password") or "")
    user = store.get_user_by_username(username)
    if not user or not security.verify_password(password, user["passwordSalt"], user["passwordHash"]):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    sanitized = security.sanitize_user(user)
    security.set_session_cookie(request, response, sanitized)
    return {"ok": True, "user": sanitized}


@router.post("/api/register")
async def register(request: Request, response: Response) -> dict:
    body = await request.json()
    users = store.list_users()
    if users and not config.ALLOW_OPEN_REGISTRATION:
        raise HTTPException(status_code=403, detail="当前系统未开放注册")
    username = security.normalize_username(body.get("username"))
    password = str(body.get("password") or "")
    if not username or len(password) < 6:
        raise HTTPException(status_code=400, detail="账号或密码不符合要求")
    if store.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="账号已存在")
    salt, password_hash = security.hash_password(password)
    role = "user"
    payload = {
        "username": username,
        "role": role,
        "permissions": DEFAULT_REGISTER_PERMISSIONS,
        "passwordSalt": salt,
        "passwordHash": password_hash,
    }
    user = store.save_user(payload)
    sanitized = security.sanitize_user(user)
    security.set_session_cookie(request, response, sanitized)
    return {"ok": True, "user": sanitized}


@router.post("/api/logout")
def logout(request: Request, response: Response) -> dict:
    security.clear_session_cookie(request, response)
    return {"ok": True}
