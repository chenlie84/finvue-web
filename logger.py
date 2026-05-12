"""操作日志记录模块."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Optional

import db


def log_action(
    action_type: str,
    module: str,
    title: str,
    description: Optional[str] = None,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    target_id: Optional[str] = None,
    target_type: Optional[str] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    request_ip: Optional[str] = None,
    request_path: Optional[str] = None,
    request_method: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    记录操作日志.
    
    Args:
        action_type: 操作类型 (login/logout/import/delete/update/error/view/create)
        module: 模块名称 (auth/operation/customers/profiles/transcripts/cases/compliance)
        title: 操作标题
        description: 详细描述
        user_id: 用户ID
        username: 用户名
        target_id: 目标对象ID
        target_type: 目标对象类型
        status: 状态 (success/failed/warning)
        error_message: 错误信息
        request_ip: 请求IP
        request_path: 请求路径
        request_method: 请求方法
        extra_data: 额外数据
    """
    try:
        db.execute(
            """
            INSERT INTO finvue_action_logs
            (user_id, username, action_type, module, title, description,
             target_id, target_type, status, error_message,
             request_ip, request_path, request_method, extra_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                username,
                action_type,
                module,
                title,
                description,
                target_id,
                target_type,
                status,
                error_message,
                request_ip,
                request_path,
                request_method,
                json.dumps(extra_data) if extra_data else None,
            )
        )
    except Exception as e:
        # 日志记录失败不应该影响主流程，只打印错误
        print(f"[Logger] Failed to log action: {e}")


def log_login(username: str, user_id: Optional[str] = None, 
              request_ip: Optional[str] = None, status: str = "success",
              error_message: Optional[str] = None) -> None:
    """记录登录日志."""
    log_action(
        action_type="login",
        module="auth",
        title=f"用户登录: {username}",
        description=f"用户 {username} 登录系统",
        user_id=user_id,
        username=username,
        status=status,
        error_message=error_message,
        request_ip=request_ip,
        request_path="/api/login",
        request_method="POST",
    )


def log_logout(username: str, user_id: Optional[str] = None,
               request_ip: Optional[str] = None) -> None:
    """记录登出日志."""
    log_action(
        action_type="logout",
        module="auth",
        title=f"用户登出: {username}",
        description=f"用户 {username} 退出系统",
        user_id=user_id,
        username=username,
        status="success",
        request_ip=request_ip,
        request_path="/api/logout",
        request_method="POST",
    )


def log_import(
    module: str,
    title: str,
    description: str,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    record_count: int = 0,
    status: str = "success",
    error_message: Optional[str] = None,
    request_ip: Optional[str] = None,
) -> None:
    """记录导入日志."""
    log_action(
        action_type="import",
        module=module,
        title=title,
        description=description,
        user_id=user_id,
        username=username,
        status=status,
        error_message=error_message,
        request_ip=request_ip,
        extra_data={"record_count": record_count},
    )


def log_delete(
    module: str,
    target_type: str,
    target_id: str,
    title: str,
    description: Optional[str] = None,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    request_ip: Optional[str] = None,
) -> None:
    """记录删除日志."""
    log_action(
        action_type="delete",
        module=module,
        title=title,
        description=description,
        user_id=user_id,
        username=username,
        target_id=target_id,
        target_type=target_type,
        status=status,
        error_message=error_message,
        request_ip=request_ip,
    )


def log_update(
    module: str,
    target_type: str,
    target_id: str,
    title: str,
    description: Optional[str] = None,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    request_ip: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
) -> None:
    """记录更新日志."""
    log_action(
        action_type="update",
        module=module,
        title=title,
        description=description,
        user_id=user_id,
        username=username,
        target_id=target_id,
        target_type=target_type,
        status=status,
        error_message=error_message,
        request_ip=request_ip,
        extra_data=extra_data,
    )


def log_create(
    module: str,
    target_type: str,
    target_id: str,
    title: str,
    description: Optional[str] = None,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    request_ip: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
) -> None:
    """记录创建日志."""
    log_action(
        action_type="create",
        module=module,
        title=title,
        description=description,
        user_id=user_id,
        username=username,
        target_id=target_id,
        target_type=target_type,
        status=status,
        error_message=error_message,
        request_ip=request_ip,
        extra_data=extra_data,
    )


def log_error(
    module: str,
    title: str,
    error_message: str,
    description: Optional[str] = None,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    request_path: Optional[str] = None,
    request_method: Optional[str] = None,
    request_ip: Optional[str] = None,
    extra_data: Optional[Dict[str, Any]] = None,
) -> None:
    """记录错误日志."""
    log_action(
        action_type="error",
        module=module,
        title=title,
        description=description,
        user_id=user_id,
        username=username,
        status="failed",
        error_message=error_message,
        request_ip=request_ip,
        request_path=request_path,
        request_method=request_method,
        extra_data=extra_data,
    )


def log_view(
    module: str,
    title: str,
    description: Optional[str] = None,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    target_id: Optional[str] = None,
    target_type: Optional[str] = None,
    request_ip: Optional[str] = None,
    request_path: Optional[str] = None,
) -> None:
    """记录查看日志."""
    log_action(
        action_type="view",
        module=module,
        title=title,
        description=description,
        user_id=user_id,
        username=username,
        target_id=target_id,
        target_type=target_type,
        status="success",
        request_ip=request_ip,
        request_path=request_path,
    )


def get_logs(
    limit: int = 100,
    offset: int = 0,
    user_id: Optional[str] = None,
    action_type: Optional[str] = None,
    module: Optional[str] = None,
    status: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> list:
    """获取日志列表."""
    where_clauses = []
    params = []
    
    if user_id:
        where_clauses.append("user_id = %s")
        params.append(user_id)
    if action_type:
        where_clauses.append("action_type = %s")
        params.append(action_type)
    if module:
        where_clauses.append("module = %s")
        params.append(module)
    if status:
        where_clauses.append("status = %s")
        params.append(status)
    if start_time:
        where_clauses.append("created_at >= %s")
        params.append(start_time)
    if end_time:
        where_clauses.append("created_at <= %s")
        params.append(end_time)
    
    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    rows = db.fetch_all(
        f"""
        SELECT id, user_id, username, action_type, module, title, description,
               target_id, target_type, status, error_message,
               request_ip, request_path, request_method, extra_data, created_at
        FROM finvue_action_logs
        WHERE {where_clause}
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params + [limit, offset])
    )
    
    return rows or []


def get_log_count(
    user_id: Optional[str] = None,
    action_type: Optional[str] = None,
    module: Optional[str] = None,
    status: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> int:
    """获取日志数量."""
    where_clauses = []
    params = []
    
    if user_id:
        where_clauses.append("user_id = %s")
        params.append(user_id)
    if action_type:
        where_clauses.append("action_type = %s")
        params.append(action_type)
    if module:
        where_clauses.append("module = %s")
        params.append(module)
    if status:
        where_clauses.append("status = %s")
        params.append(status)
    if start_time:
        where_clauses.append("created_at >= %s")
        params.append(start_time)
    if end_time:
        where_clauses.append("created_at <= %s")
        params.append(end_time)
    
    where_clause = " AND ".join(where_clauses) if where_clauses else "1=1"
    
    row = db.fetch_one(
        f"SELECT COUNT(*) as count FROM finvue_action_logs WHERE {where_clause}",
        tuple(params)
    )
    
    return row.get("count", 0) if row else 0