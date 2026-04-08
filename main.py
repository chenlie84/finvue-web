from pathlib import Path
from datetime import datetime
from typing import List

import httpx
from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from db_utils import fetch_customer_activity
from pages.registry import PageRegistry
from config import MODEL, API_KEY


BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def format_percent(value) -> str:
    if value is None:
        return "0.00%"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "0.00%"


templates.env.filters["percent"] = format_percent

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """首页显示所有页面列表"""
    pages = PageRegistry.get_all()
    context = {
        "request": request,
        "pages": [
            {"id": page.page_id, "title": page.title}
            for page in pages.values()
        ]
    }
    return templates.TemplateResponse("index.html", context)


@app.get("/api/customer_activity")
async def get_customer_activity(
    customer_code: str = Query(..., description="客户编号"),
):
    """
    查询客户活跃度接口

    传参 customer_code，返回 customer_code, flag_activity, dt
    """
    rows = fetch_customer_activity(customer_code)
    # 将 datetime 转为字符串以便 JSON 序列化
    for row in rows:
        if "dt" in row and isinstance(row["dt"], datetime):
            row["dt"] = row["dt"].strftime("%Y-%m-%d %H:%M:%S")
    return {"data": rows}


# ========== Chat API ==========

QWEN_API_URL = "http://aigc-api.aigc.paas.idc/v1/chat/completions"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[ChatMessage]


@app.post("/api/chat")
async def chat_stream(req: ChatRequest):
    """
    流式聊天接口，代理请求到 Qwen 大模型 API
    """
    payload = {
        "model": MODEL,
        "messages": [m.model_dump() for m in req.messages],
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    async def event_generator():
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", QWEN_API_URL, json=payload, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    yield f"data: {{\"error\": \"{body.decode()}\"}}"
                    return
                async for line in resp.aiter_lines():
                    if line:
                        yield line + "\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ========== LLM Proxy API ==========

class ProxyRequest(BaseModel):
    """
    通用模型中转请求，格式兼容 OpenAI chat/completions。
    客户端需额外传入 api_key 用于鉴权。
    """
    model: str
    api_key: str
    messages: List[ChatMessage]
    temperature: float = 1.0
    max_tokens: int = 2048
    stream: bool = True


@app.post("/v1/chat/completions")
async def proxy_chat_completions(req: ProxyRequest):
    """
    模型中转接口 —— 格式兼容 OpenAI chat/completions。

    客户端传入 model、api_key、messages 等参数，
    服务端转发到内部 AIGC API 并将响应原样返回。
    """
    payload = {
        "model": req.model,
        "messages": [m.model_dump() for m in req.messages],
        "temperature": req.temperature,
        "max_tokens": req.max_tokens,
        "stream": req.stream,
    }
    headers = {
        "Authorization": f"Bearer {req.api_key}",
        "Content-Type": "application/json",
    }

    if req.stream:
        # 流式响应
        async def proxy_stream():
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST", QWEN_API_URL, json=payload, headers=headers
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        yield f"data: {{\"error\": \"{body.decode()}\"}}\n\n"
                        return
                    async for line in resp.aiter_lines():
                        if line:
                            yield line + "\n"

        return StreamingResponse(
            proxy_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        # 非流式响应，直接返回 JSON
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                QWEN_API_URL, json=payload, headers=headers
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=resp.text,
                )
            return resp.json()


@app.get("/{page_id}", response_class=HTMLResponse)
async def get_page(request: Request, page_id: str):
    """
    页面视图
    
    Args:
        page_id: 页面ID (例如: crs, sales)
    """
    try:
        page = PageRegistry.get(page_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Page '{page_id}' not found")
    
    context = page.get_context()
    context["request"] = request
    
    return templates.TemplateResponse(page.template, context)


def get_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)

