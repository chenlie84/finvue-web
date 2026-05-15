from __future__ import annotations

import json
import os
import uuid
from typing import Any, Dict, Optional

import ai_router
import db
import security
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse

router = APIRouter()


# ══════════════ 会话管理 ══════════════

@router.get("/api/ai-chat/sessions")
async def list_sessions(session: dict = Depends(security.require_auth)) -> list[dict[str, Any]]:
    """获取用户的会话列表"""
    username = session.get("username")
    sql = """
        SELECT session_id, title, system_prompt, model, created_at, updated_at
        FROM finvue_ai_chat_sessions
        WHERE created_by = %s AND is_deleted = 0
        ORDER BY updated_at DESC
        LIMIT 50
    """
    return db.fetch_all(sql, (username,))


@router.post("/api/ai-chat/sessions")
async def create_session(request: Request, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """创建新会话"""
    body = await request.json()
    username = session.get("username")
    session_id = f"chat_{uuid.uuid4().hex[:16]}"
    
    sql = """
        INSERT INTO finvue_ai_chat_sessions (session_id, title, system_prompt, model, created_by)
        VALUES (%s, %s, %s, %s, %s)
    """
    db.execute(sql, (
        session_id,
        body.get("title", "新对话"),
        body.get("systemPrompt", ""),
        body.get("model", ""),
        username
    ))
    
    return {"sessionId": session_id, "title": body.get("title", "新对话")}


@router.put("/api/ai-chat/sessions/{session_id}")
async def update_session(session_id: str, request: Request, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """更新会话"""
    body = await request.json()
    username = session.get("username")
    
    sql = """
        UPDATE finvue_ai_chat_sessions 
        SET title = %s, system_prompt = %s, model = %s
        WHERE session_id = %s AND created_by = %s AND is_deleted = 0
    """
    db.execute(sql, (
        body.get("title"),
        body.get("systemPrompt"),
        body.get("model"),
        session_id,
        username
    ))
    
    return {"ok": True}


@router.delete("/api/ai-chat/sessions/{session_id}")
async def delete_session(session_id: str, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """删除会话"""
    username = session.get("username")
    sql = "UPDATE finvue_ai_chat_sessions SET is_deleted = 1 WHERE session_id = %s AND created_by = %s"
    db.execute(sql, (session_id, username))
    return {"ok": True}


# ══════════════ 消息管理 ══════════════

@router.get("/api/ai-chat/messages/{session_id}")
async def get_messages(session_id: str, session: dict = Depends(security.require_auth)) -> list[dict[str, Any]]:
    """获取会话消息"""
    username = session.get("username")
    
    # 验证会话属于当前用户
    check_sql = "SELECT session_id FROM finvue_ai_chat_sessions WHERE session_id = %s AND created_by = %s AND is_deleted = 0"
    if not db.fetch_one(check_sql, (session_id, username)):
        raise HTTPException(status_code=404, detail="会话不存在")
    
    sql = """
        SELECT id, role, content, model, tokens, created_at
        FROM finvue_ai_chat_messages
        WHERE session_id = %s
        ORDER BY created_at ASC
    """
    return db.fetch_all(sql, (session_id,))


@router.post("/api/ai-chat/messages")
async def send_message(request: Request, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """发送消息并获取AI回复"""
    body = await request.json()
    username = session.get("username")
    
    session_id = body.get("sessionId")
    user_message = body.get("message", "").strip()
    
    if not user_message:
        raise HTTPException(status_code=400, detail="消息不能为空")
    
    # 如果没有session_id，创建新会话
    if not session_id:
        session_id = f"chat_{uuid.uuid4().hex[:16]}"
        db.execute("""
            INSERT INTO finvue_ai_chat_sessions (session_id, title, system_prompt, created_by)
            VALUES (%s, %s, %s, %s)
        """, (session_id, "新对话", body.get("systemPrompt", ""), username))
    
    # 验证会话属于当前用户
    check_sql = "SELECT session_id, system_prompt FROM finvue_ai_chat_sessions WHERE session_id = %s AND created_by = %s AND is_deleted = 0"
    chat_session = db.fetch_one(check_sql, (session_id, username))
    if not chat_session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    # 保存用户消息
    db.execute("""
        INSERT INTO finvue_ai_chat_messages (session_id, role, content)
        VALUES (%s, 'user', %s)
    """, (session_id, user_message))
    
    # 获取历史消息构建上下文
    history_sql = """
        SELECT role, content FROM finvue_ai_chat_messages
        WHERE session_id = %s
        ORDER BY created_at ASC
    """
    history = db.fetch_all(history_sql, (session_id,))
    
    # 构建系统提示词
    system_prompt = body.get("systemPrompt") or chat_session.get("system_prompt") or ""
    
    # 如果有知识库内容，附加到系统提示词
    knowledge_context = ""
    if body.get("knowledgeBaseId"):
        kb_sql = "SELECT content FROM finvue_ai_knowledge_base WHERE id = %s AND created_by = %s AND status = 'ready'"
        kb = db.fetch_one(kb_sql, (body.get("knowledgeBaseId"), username))
        if kb and kb.get("content"):
            knowledge_context = f"\n\n【知识库内容】\n{kb['content']}\n"
    
    # 调用AI生成回复
    try:
        payload = {
            "systemPrompt": system_prompt + knowledge_context,
            "userPrompt": user_message,
            "model": body.get("model", ""),
        }
        
        # 添加历史消息作为上下文
        if history:
            context_parts = []
            for msg in history[-10:]:  # 保留最近10条消息
                role = msg.get("role", "user")
                content = msg.get("content", "")
                context_parts.append(f"{role}: {content}")
            payload["userPrompt"] = f"【对话历史】\n" + "\n".join(context_parts) + f"\n\n【当前问题】\n{user_message}"
        
        result = ai_router.generate(payload, username=username)
        ai_response = result.get("markdown", "")
        
    except Exception as e:
        ai_response = f"抱歉，发生错误：{str(e)}"
    
    # 保存AI回复
    db.execute("""
        INSERT INTO finvue_ai_chat_messages (session_id, role, content, model)
        VALUES (%s, 'assistant', %s, %s)
    """, (session_id, ai_response, body.get("model", "")))
    
    # 更新会话标题（如果是第一条消息）
    if len(history) == 0:
        title = user_message[:30] + ("..." if len(user_message) > 30 else "")
        db.execute("UPDATE finvue_ai_chat_sessions SET title = %s WHERE session_id = %s", (title, session_id))
    
    # 更新会话时间
    db.execute("UPDATE finvue_ai_chat_sessions SET updated_at = NOW() WHERE session_id = %s", (session_id,))
    
    return {
        "sessionId": session_id,
        "message": ai_response,
        "history": history + [{"role": "user", "content": user_message}, {"role": "assistant", "content": ai_response}]
    }


@router.post("/api/ai-chat/messages/stream")
async def stream_message(request: Request, session: dict = Depends(security.require_auth)) -> StreamingResponse:
    """流式发送消息"""
    body = await request.json()
    username = session.get("username")
    
    session_id = body.get("sessionId")
    user_message = body.get("message", "").strip()
    
    if not user_message:
        raise HTTPException(status_code=400, detail="消息不能为空")
    
    # 如果没有session_id，创建新会话
    if not session_id:
        session_id = f"chat_{uuid.uuid4().hex[:16]}"
        db.execute("""
            INSERT INTO finvue_ai_chat_sessions (session_id, title, system_prompt, created_by)
            VALUES (%s, %s, %s, %s)
        """, (session_id, "新对话", body.get("systemPrompt", ""), username))
    
    # 保存用户消息
    db.execute("""
        INSERT INTO finvue_ai_chat_messages (session_id, role, content)
        VALUES (%s, 'user', %s)
    """, (session_id, user_message))
    
    # 构建提示词
    system_prompt = body.get("systemPrompt", "")
    knowledge_context = ""
    if body.get("knowledgeBaseId"):
        kb_sql = "SELECT content FROM finvue_ai_knowledge_base WHERE id = %s AND created_by = %s AND status = 'ready'"
        kb = db.fetch_one(kb_sql, (body.get("knowledgeBaseId"), username))
        if kb and kb.get("content"):
            knowledge_context = f"\n\n【知识库内容】\n{kb['content']}\n"
    
    def events():
        full_response = ""
        try:
            payload = {
                "systemPrompt": system_prompt + knowledge_context,
                "userPrompt": user_message,
                "model": body.get("model", ""),
            }
            
            result = ai_router.generate(payload, username=username)
            ai_response = result.get("markdown", "")
            
            # 流式输出
            for i in range(0, len(ai_response), 50):
                chunk = ai_response[i:i + 50]
                full_response += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'content': chunk}, ensure_ascii=False)}\n\n"
            
            # 保存AI回复
            db.execute("""
                INSERT INTO finvue_ai_chat_messages (session_id, role, content, model)
                VALUES (%s, 'assistant', %s, %s)
            """, (session_id, full_response, body.get("model", "")))
            
            # 更新会话标题
            title = user_message[:30] + ("..." if len(user_message) > 30 else "")
            db.execute("UPDATE finvue_ai_chat_sessions SET title = %s WHERE session_id = %s", (title, session_id))
            
            yield f"data: {json.dumps({'type': 'done', 'sessionId': session_id}, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            error_msg = str(e)
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(events(), media_type="application/x-ndjson; charset=utf-8")


# ══════════════ 提示词模板管理 ══════════════

@router.get("/api/ai-chat/prompts")
async def list_prompts(session: dict = Depends(security.require_auth)) -> list[dict[str, Any]]:
    """获取提示词模板列表"""
    username = session.get("username")
    sql = """
        SELECT id, name, description, content, category, is_system, is_default
        FROM finvue_ai_prompt_templates
        WHERE created_by = %s OR is_system = 1
        ORDER BY is_system DESC, is_default DESC, created_at DESC
    """
    return db.fetch_all(sql, (username,))


@router.post("/api/ai-chat/prompts")
async def create_prompt(request: Request, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """创建提示词模板"""
    body = await request.json()
    username = session.get("username")
    
    sql = """
        INSERT INTO finvue_ai_prompt_templates (name, description, content, category, is_system, created_by)
        VALUES (%s, %s, %s, %s, 0, %s)
    """
    result = db.execute(sql, (
        body.get("name"),
        body.get("description", ""),
        body.get("content", ""),
        body.get("category", "general"),
        username
    ))
    
    return {"id": result, "name": body.get("name")}


@router.put("/api/ai-chat/prompts/{prompt_id}")
async def update_prompt(prompt_id: int, request: Request, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """更新提示词模板"""
    body = await request.json()
    username = session.get("username")
    
    sql = """
        UPDATE finvue_ai_prompt_templates 
        SET name = %s, description = %s, content = %s, category = %s
        WHERE id = %s AND created_by = %s
    """
    db.execute(sql, (
        body.get("name"),
        body.get("description", ""),
        body.get("content", ""),
        body.get("category", "general"),
        prompt_id,
        username
    ))
    
    return {"ok": True}


@router.delete("/api/ai-chat/prompts/{prompt_id}")
async def delete_prompt(prompt_id: int, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """删除提示词模板"""
    username = session.get("username")
    sql = "DELETE FROM finvue_ai_prompt_templates WHERE id = %s AND created_by = %s AND is_system = 0"
    db.execute(sql, (prompt_id, username))
    return {"ok": True}


# ══════════════ 知识库管理 ══════════════

@router.get("/api/ai-chat/knowledge")
async def list_knowledge(session: dict = Depends(security.require_auth)) -> list[dict[str, Any]]:
    """获取知识库列表"""
    username = session.get("username")
    sql = """
        SELECT id, name, description, file_name, file_type, file_size, status, created_at
        FROM finvue_ai_knowledge_base
        WHERE created_by = %s
        ORDER BY created_at DESC
    """
    return db.fetch_all(sql, (username,))


@router.post("/api/ai-chat/knowledge")
async def upload_knowledge(
    request: Request,
    file: UploadFile = File(...),
    session: dict = Depends(security.require_auth)
) -> dict[str, Any]:
    """上传知识库文件"""
    username = session.get("username")
    
    # 读取文件内容
    content = await file.read()
    file_size = len(content)
    file_type = file.filename.split(".")[-1].lower() if "." in file.filename else ""
    
    # 尝试提取文本内容
    text_content = ""
    try:
        if file_type in ["txt", "md", "markdown"]:
            text_content = content.decode("utf-8")
        elif file_type == "json":
            text_content = content.decode("utf-8")
        else:
            # 其他类型只存储基本信息
            text_content = f"[{file_type.upper()} 文件，大小 {file_size} bytes]"
    except:
        text_content = f"[文件，大小 {file_size} bytes]"
    
    # 截取前10000字符作为摘要
    content_summary = text_content[:10000] if len(text_content) > 10000 else text_content
    
    sql = """
        INSERT INTO finvue_ai_knowledge_base (name, description, file_name, file_type, file_size, content, status, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, 'ready', %s)
    """
    result = db.execute(sql, (
        file.filename,
        "",
        file.filename,
        file_type,
        file_size,
        content_summary,
        username
    ))
    
    return {"id": result, "name": file.filename, "status": "ready"}


@router.delete("/api/ai-chat/knowledge/{knowledge_id}")
async def delete_knowledge(knowledge_id: int, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """删除知识库"""
    username = session.get("username")
    sql = "DELETE FROM finvue_ai_knowledge_base WHERE id = %s AND created_by = %s"
    db.execute(sql, (knowledge_id, username))
    return {"ok": True}


@router.get("/api/ai-chat/knowledge/{knowledge_id}/content")
async def get_knowledge_content(knowledge_id: int, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """获取知识库详细内容"""
    username = session.get("username")
    sql = "SELECT id, name, content, file_name FROM finvue_ai_knowledge_base WHERE id = %s AND created_by = %s"
    kb = db.fetch_one(sql, (knowledge_id, username))
    
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    
    return {"id": kb["id"], "name": kb["name"], "content": kb["content"]}


# ══════════════ 系统提示词 ══════════════

@router.get("/api/ai-chat/system-prompts")
async def get_system_prompts() -> list[dict[str, Any]]:
    """获取系统预置提示词（无需登录）"""
    sql = """
        SELECT id, name, description, content, category
        FROM finvue_ai_prompt_templates
        WHERE is_system = 1
        ORDER BY category, name
    """
    return db.fetch_all(sql, ())


# ══════════════ 兼容 OpenAI Chat API ══════════════

@router.post("/api/ai-chat/chat")
async def chat_completion(request: Request, session: dict = Depends(security.require_auth)) -> dict[str, Any]:
    """OpenAI 兼容的 Chat API"""
    body = await request.json()
    username = session.get("username")
    
    messages = body.get("messages", [])
    if not messages:
        raise HTTPException(status_code=400, detail="messages is required")
    
    # 提取 system prompt
    system_prompt = ""
    filtered_messages = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_prompt = content
        else:
            filtered_messages.append(msg)
    
    # 构建用户消息
    user_prompt = "\n".join(str(msg.get("content", "")) for msg in filtered_messages if msg.get("role") == "user")
    
    # 调用AI
    try:
        payload = {
            "systemPrompt": system_prompt,
            "userPrompt": user_prompt,
            "model": body.get("model", ""),
        }
        result = ai_router.generate(payload, username=username)
        ai_response = result.get("markdown", "")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(__import__("time").time()),
        "model": body.get("model", "gpt-3.5-turbo"),
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": ai_response
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": len(system_prompt + user_prompt) // 4,
            "completion_tokens": len(ai_response) // 4,
            "total_tokens": (len(system_prompt + user_prompt) + len(ai_response)) // 4
        }
    }
