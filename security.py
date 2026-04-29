"""Authentication, password hashing and cookie session helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request, Response

import config
import db
import store


def normalize_username(username: Optional[str]) -> str:
    return str(username or "").strip().lower()


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha512", password.encode(), salt.encode(), 100000, dklen=64).hex()
    return salt, digest


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    _, digest = hash_password(password, salt)
    return hmac.compare_digest(digest, expected_hash)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _mysql_datetime_from_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _iso(value: Any) -> str:
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return str(value)


def create_session(user: Dict[str, Any]) -> str:
    token = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")
    expires_at = _now_ms() + config.SESSION_TTL_SECONDS * 1000
    db.execute(
        """
        INSERT INTO sessions (token_hash, username, role, expires_at)
        VALUES (%s, %s, %s, %s)
        """,
        (_token_hash(token), user["username"], user.get("role", "user"), _mysql_datetime_from_ms(expires_at)),
    )
    return token


def set_session_cookie(request: Request, response: Response, user: Dict[str, Any]) -> None:
    token = create_session(user)
    response.set_cookie(
        config.SESSION_COOKIE_NAME,
        token,
        max_age=config.SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.headers.get("x-forwarded-proto") == "https",
        path="/",
    )


def clear_session_cookie(request: Request, response: Response) -> None:
    token = request.cookies.get(config.SESSION_COOKIE_NAME, "")
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash = %s", (_token_hash(token),))
    response.delete_cookie(config.SESSION_COOKIE_NAME, path="/")


def get_session(request: Request) -> Optional[Dict[str, Any]]:
    token = request.cookies.get(config.SESSION_COOKIE_NAME, "")
    if not token:
        return None
    row = db.fetch_one(
        """
        SELECT token_hash, username, role, expires_at, created_at
        FROM sessions
        WHERE token_hash = %s AND expires_at > CURRENT_TIMESTAMP
        """,
        (_token_hash(token),),
    )
    if not row:
        return None
    user = store.get_user_by_username(row["username"])
    if not user:
        return None
    return {
        "username": user["username"],
        "role": user["role"],
        "permissions": user.get("permissions") or store.normalize_user_permissions(user.get("role", "user")),
        "expiresAt": int(row["expires_at"].replace(tzinfo=timezone.utc).timestamp() * 1000),
        "createdAt": user.get("createdAt") or _iso(row.get("created_at")),
    }


def require_auth(request: Request) -> Dict[str, Any]:
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return session


def require_admin(request: Request) -> Dict[str, Any]:
    session = require_auth(request)
    if session.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return session


def has_permission(session: Dict[str, Any], permission: str) -> bool:
    if session.get("role") == "admin":
        return True
    permissions = session.get("permissions") if isinstance(session.get("permissions"), dict) else {}
    return bool(permissions.get(permission))


def require_permission(permission: str):
    def _dependency(request: Request) -> Dict[str, Any]:
        session = require_auth(request)
        if not has_permission(session, permission):
            raise HTTPException(status_code=403, detail=f"当前账号没有“{permission}”模块权限")
        return session

    return _dependency


def require_any_permission(*permissions: str):
    def _dependency(request: Request) -> Dict[str, Any]:
        session = require_auth(request)
        if session.get("role") == "admin":
            return session
        for permission in permissions:
            if has_permission(session, permission):
                return session
        raise HTTPException(status_code=403, detail="当前账号没有访问该功能的权限")

    return _dependency


def sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    role = user.get("role", "user")
    return {
        "username": user["username"],
        "role": role,
        "permissions": store.normalize_user_permissions(role, user.get("permissions")),
        "createdAt": user.get("createdAt", ""),
    }
