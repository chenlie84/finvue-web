"""操作日志API."""
from typing import Optional
from fastapi import APIRouter, Depends, Request
import security
import logger

router = APIRouter()


@router.get("/api/logs")
def get_logs_api(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    action_type: Optional[str] = None,
    module: Optional[str] = None,
    status: Optional[str] = None,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """获取操作日志列表."""
    logs = logger.get_logs(
        limit=min(limit, 500),
        offset=offset,
        action_type=action_type,
        module=module,
        status=status,
    )
    
    count = logger.get_log_count(
        action_type=action_type,
        module=module,
        status=status,
    )
    
    # 格式化日志
    formatted_logs = []
    for log in logs:
        # 获取IP地址
        ip = log.get("request_ip") or ""
        if not ip:
            forwarded = request.headers.get("X-Forwarded-For", "")
            ip = forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else ""
        
        formatted_logs.append({
            "id": log.get("id"),
            "user_id": log.get("user_id"),
            "username": log.get("username") or "未知用户",
            "action_type": log.get("action_type"),
            "module": log.get("module"),
            "title": log.get("title"),
            "description": log.get("description"),
            "target_id": log.get("target_id"),
            "target_type": log.get("target_type"),
            "status": log.get("status"),
            "error_message": log.get("error_message"),
            "request_ip": ip,
            "request_path": log.get("request_path"),
            "request_method": log.get("request_method"),
            "extra_data": log.get("extra_data"),
            "created_at": str(log.get("created_at") or ""),
        })
    
    return {
        "ok": True,
        "logs": formatted_logs,
        "count": count,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/api/logs")
def clear_logs_api(
    request: Request,
    days: int = 30,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """清理旧日志（保留最近N天）."""
    import db
    from datetime import datetime, timedelta
    
    cutoff = datetime.now() - timedelta(days=days)
    cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")
    
    db.execute(
        "DELETE FROM finvue_action_logs WHERE created_at < %s",
        (cutoff_str,)
    )
    
    # 记录清理操作
    session = security.require_auth(request)
    logger.log_action(
        action_type="delete",
        module="logs",
        title="清理操作日志",
        description=f"清理了 {days} 天前的旧日志",
        user_id=session.get("user_id"),
        username=session.get("username"),
        status="success",
    )
    
    return {"ok": True, "message": f"已清理 {days} 天前的日志"}