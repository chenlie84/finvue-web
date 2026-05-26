from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

import config
import security
import store
import logger


router = APIRouter()


def get_client_ip(request: Request) -> str:
    """获取客户端IP地址."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


DEFAULT_REGISTER_PERMISSIONS = {
    "home": True,
    "ai-chat": True,
    "live": True,
}


@router.get("/api/session")
def session(request: Request) -> dict:
    current = security.get_session(request)
    access = store.get_access_settings(config.ALLOW_OPEN_REGISTRATION)
    return {"authenticated": bool(current), "user": current, "registrationEnabled": bool(access.get("openRegistration"))}


@router.post("/api/login")
async def login(request: Request, response: Response) -> dict:
    body = await request.json()
    username = security.normalize_username(body.get("username"))
    password = str(body.get("password") or "")
    ip = get_client_ip(request)
    
    user = store.get_user_by_username(username)
    if not user or not security.verify_password(password, user["passwordSalt"], user["passwordHash"]):
        # 记录登录失败
        logger.log_login(username=username, request_ip=ip, status="failed", error_message="账号或密码错误")
        raise HTTPException(status_code=401, detail="账号或密码错误")
    
    sanitized = security.sanitize_user(user)
    security.set_session_cookie(request, response, sanitized)
    
    # 记录登录成功
    logger.log_login(username=username, user_id=user.get("id"), request_ip=ip, status="success")
    
    return {"ok": True, "user": sanitized}


@router.post("/api/register")
async def register(request: Request, response: Response) -> dict:
    body = await request.json()
    users = store.list_users()
    access = store.get_access_settings(config.ALLOW_OPEN_REGISTRATION)
    if users and not access.get("openRegistration"):
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
    
    # 记录注册
    ip = get_client_ip(request)
    logger.log_create(
        module="auth",
        target_type="user",
        target_id=user.get("id"),
        title=f"用户注册: {username}",
        description=f"新用户 {username} 注册成功",
        username=username,
        user_id=user.get("id"),
        request_ip=ip,
    )
    
    return {"ok": True, "user": sanitized}


@router.post("/api/logout")
def logout(request: Request, response: Response) -> dict:
    session = security.get_session(request)
    username = session.get("username") if session else "未知用户"
    user_id = session.get("user_id") if session else None
    ip = get_client_ip(request)
    
    security.clear_session_cookie(request, response)
    
    # 记录登出
    logger.log_logout(username=username, user_id=user_id, request_ip=ip)
    
    return {"ok": True}
