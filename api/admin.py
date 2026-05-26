from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
import pymysql

import db
import config
import migrate
import security
import store


router = APIRouter()


def _remote_db_with_env_fallback() -> dict:
    saved = store.get_remote_db_settings()
    has_saved = bool(saved.get("host") or saved.get("database") or saved.get("user"))
    if has_saved:
        return {**saved, "source": "admin"}
    return {
        "enabled": True,
        "host": config.REMOTE_DB_HOST,
        "port": config.REMOTE_DB_PORT,
        "database": config.REMOTE_DB_DATABASE,
        "user": config.REMOTE_DB_USER,
        "password": config.REMOTE_DB_PASSWORD,
        "updatedAt": "",
        "updatedBy": "",
        "source": "env" if config.has_remote_db_config() else "empty",
    }


def _mask_remote_db_settings(settings: dict) -> dict:
    masked = {key: value for key, value in settings.items() if key != "password"}
    masked["hasPassword"] = bool(settings.get("password"))
    if settings.get("password"):
        masked["password"] = "********"
    else:
        masked["password"] = ""
    masked["configured"] = bool(masked.get("enabled") and masked.get("host") and masked.get("database") and masked.get("user"))
    return masked


def _remote_db_connection(settings: dict):
    return pymysql.connect(
        host=settings.get("host") or "",
        port=int(settings.get("port") or 3306),
        user=settings.get("user") or "",
        password=settings.get("password") or "",
        database=settings.get("database") or "",
        connect_timeout=8,
        read_timeout=8,
        write_timeout=8,
        charset="utf8mb4",
    )


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


@router.get("/api/admin/remote-db")
def get_remote_db(_: dict = Depends(security.require_admin)) -> dict:
    settings = _remote_db_with_env_fallback()
    return {"ok": True, "settings": _mask_remote_db_settings(settings)}


@router.put("/api/admin/remote-db")
async def put_remote_db(request: Request, session: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    incoming = store.safe_object(incoming)
    if incoming.get("password") == "********":
        incoming = {**incoming, "password": _remote_db_with_env_fallback().get("password", "")}
    saved = store.save_remote_db_settings(incoming, session.get("username", ""))
    return {"ok": True, "settings": _mask_remote_db_settings({**saved, "source": "admin"})}


@router.post("/api/admin/remote-db/test")
async def test_remote_db(request: Request, _: dict = Depends(security.require_admin)) -> dict:
    body = await request.json()
    incoming = body.get("settings") if isinstance(body.get("settings"), dict) else body
    current = _remote_db_with_env_fallback()
    candidate = {**current, **store.safe_object(incoming)}
    if candidate.get("password") == "********":
        candidate["password"] = current.get("password", "")
    missing = [label for key, label in (("host", "主机"), ("database", "数据库"), ("user", "用户名")) if not store.text(candidate.get(key))]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少必填项：{'、'.join(missing)}")
    try:
        conn = _remote_db_connection(candidate)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()
        return {"ok": True, "message": "连接成功"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"连接失败：{exc}") from exc


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
