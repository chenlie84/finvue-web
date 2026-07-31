from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

import config
import security
import store
import logger
from services import feishu_push


router = APIRouter()
LOGIN_FAILURE_LIMIT = 5
LOGIN_LOCK_MINUTES = 10
_LOGIN_FAILURES: dict[str, dict] = {}


def get_client_ip(request: Request) -> str:
    """获取客户端IP地址."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _login_key(ip: str, username: str) -> str:
    return f"{ip or 'unknown'}:{username or 'unknown'}".lower()


def _check_login_limit(ip: str, username: str) -> None:
    key = _login_key(ip, username)
    entry = _LOGIN_FAILURES.get(key) or {}
    locked_until = entry.get("locked_until")
    now = datetime.now(timezone.utc)
    if isinstance(locked_until, datetime) and now < locked_until:
        remain = int((locked_until - now).total_seconds() // 60) + 1
        raise HTTPException(status_code=429, detail=f"登录失败次数过多，请 {remain} 分钟后再试")
    if isinstance(locked_until, datetime) and now >= locked_until:
        _LOGIN_FAILURES.pop(key, None)


def _record_login_failure(ip: str, username: str) -> None:
    key = _login_key(ip, username)
    now = datetime.now(timezone.utc)
    entry = _LOGIN_FAILURES.get(key) or {"count": 0}
    count = int(entry.get("count") or 0) + 1
    payload = {"count": count, "last_failed_at": now}
    if count >= LOGIN_FAILURE_LIMIT:
        payload["locked_until"] = now + timedelta(minutes=LOGIN_LOCK_MINUTES)
    _LOGIN_FAILURES[key] = payload


def _clear_login_failures(ip: str, username: str) -> None:
    _LOGIN_FAILURES.pop(_login_key(ip, username), None)


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
    _check_login_limit(ip, username)
    
    user = store.get_user_by_username(username)
    if not user or not security.verify_password(password, user["passwordSalt"], user["passwordHash"]):
        _record_login_failure(ip, username)
        # 记录登录失败
        logger.log_login(username=username, request_ip=ip, status="failed", error_message="账号或密码错误")
        raise HTTPException(status_code=401, detail="账号或密码错误")
    
    sanitized = security.sanitize_user(user)
    security.set_session_cookie(request, response, sanitized)
    _clear_login_failures(ip, username)
    
    # 记录登录成功
    logger.log_login(username=username, user_id=user.get("id"), request_ip=ip, status="success")
    
    return {"ok": True, "user": sanitized}


@router.post("/api/register")
async def register(request: Request, response: Response, background_tasks: BackgroundTasks) -> dict:
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
    background_tasks.add_task(feishu_push.notify_registration_safe, sanitized, ip)
    
    return {"ok": True, "user": sanitized}


@router.post("/api/me/password")
async def change_password(request: Request) -> dict:
    session = security.require_auth(request)
    body = await request.json()
    username = security.normalize_username(session.get("username"))
    current_password = str(body.get("currentPassword") or body.get("oldPassword") or "")
    new_password = str(body.get("newPassword") or "")
    ip = get_client_ip(request)

    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码至少需要 6 位")
    if current_password == new_password:
        raise HTTPException(status_code=400, detail="新密码不能和当前密码相同")

    user = store.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not security.verify_password(current_password, user["passwordSalt"], user["passwordHash"]):
        logger.log_update(
            module="auth",
            target_type="user",
            target_id=username,
            title="修改密码失败",
            description=f"用户 {username} 修改密码时旧密码校验失败",
            username=username,
            request_ip=ip,
            status="failed",
            error_message="当前密码错误",
        )
        raise HTTPException(status_code=400, detail="当前密码错误")

    salt, password_hash = security.hash_password(new_password)
    store.save_user({
        **user,
        "passwordSalt": salt,
        "passwordHash": password_hash,
    })
    logger.log_update(
        module="auth",
        target_type="user",
        target_id=username,
        title="用户修改密码",
        description=f"用户 {username} 已修改自己的登录密码",
        username=username,
        request_ip=ip,
    )
    return {"ok": True}


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
