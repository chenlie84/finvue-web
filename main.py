"""FinVue FastAPI production entrypoint."""
from __future__ import annotations

import asyncio
import logging
import mimetypes
from uuid import uuid4
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

import config
import migrate
from api import admin, ai, auth, customers, daily_review, data_collection, files, jobs, libraries, reports, settings, sop, system, logs, ai_chat, hotspot, market, backtest, feishu
from api import operation as api_operation


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    hotspot_stop_event: asyncio.Event | None = None
    hotspot_task: asyncio.Task | None = None
    market_stop_event: asyncio.Event | None = None
    market_task: asyncio.Task | None = None
    feishu_stop_event: asyncio.Event | None = None
    feishu_task: asyncio.Task | None = None
    daily_review_stop_event: asyncio.Event | None = None
    daily_review_task: asyncio.Task | None = None
    print(f"[lifespan] AUTO_MIGRATE={config.AUTO_MIGRATE}, ENV={config.ENV}, has_mysql={config.has_mysql_config()}")
    if config.IS_PRODUCTION and config.AUTH_SECRET == "dev-only-local-auth-secret":
        logger.critical("[security] AUTH_SECRET is using the development default in production; override it immediately.")
    if config.AUTO_MIGRATE and config.has_mysql_config() and config.ENV.lower() != "test":
        print("[lifespan] Running migrations...")
        try:
            ran = migrate.run_migrations()
            print(f"[lifespan] Migrations ran: {ran}")
        except Exception as e:
            print(f"[lifespan] Migration error: {e}")
    else:
        print("[lifespan] Skipping migrations")
    if not config.has_ceph_config():
        config.OBJECT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    if config.has_mysql_config() and config.HOTSPOT_API_ENABLED and config.ENV.lower() != "test":
        from services.hotspot_scheduler import run_scheduler
        hotspot_stop_event = asyncio.Event()
        hotspot_task = asyncio.create_task(run_scheduler(hotspot_stop_event))
    if config.has_mysql_config() and config.ENV.lower() != "test":
        from services.market_scheduler import run_scheduler as run_market_scheduler
        market_stop_event = asyncio.Event()
        market_task = asyncio.create_task(run_market_scheduler(market_stop_event))
        from services.feishu_scheduler import run_scheduler as run_feishu_scheduler
        feishu_stop_event = asyncio.Event()
        feishu_task = asyncio.create_task(run_feishu_scheduler(feishu_stop_event))
        from services.daily_review_scheduler import run_scheduler as run_daily_review_scheduler
        daily_review_stop_event = asyncio.Event()
        daily_review_task = asyncio.create_task(run_daily_review_scheduler(daily_review_stop_event))
    try:
        yield
    finally:
        if hotspot_stop_event and hotspot_task:
            hotspot_stop_event.set()
            hotspot_task.cancel()
            try:
                await hotspot_task
            except asyncio.CancelledError:
                pass
        if market_stop_event and market_task:
            market_stop_event.set()
            market_task.cancel()
            try:
                await market_task
            except asyncio.CancelledError:
                pass
        if feishu_stop_event and feishu_task:
            feishu_stop_event.set()
            feishu_task.cancel()
            try:
                await feishu_task
            except asyncio.CancelledError:
                pass
        if daily_review_stop_event and daily_review_task:
            daily_review_stop_event.set()
            daily_review_task.cancel()
            try:
                await daily_review_task
            except asyncio.CancelledError:
                pass


app = FastAPI(title="FinVue", version="2.0.0-fastapi", lifespan=lifespan)
templates = Jinja2Templates(directory=str(config.APP_DIR))

# 自托管字体 /static/vendor/fonts/*.woff2：容器里 Python 的 mimetypes 表不认识 woff2，
# Starlette 会退化成 text/plain。按规范显式注册为 font/woff2（woff/ttf 一并补上），
# 避免不同运行环境（本地容器 vs Northflank）猜出来的类型不一致。
for _ext, _mime in ((".woff2", "font/woff2"), (".woff", "font/woff"), (".ttf", "font/ttf")):
    if mimetypes.guess_type("x" + _ext)[0] != _mime:
        mimetypes.add_type(_mime, _ext)

if config.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(jobs.router)
app.include_router(libraries.router)
app.include_router(customers.router)
app.include_router(daily_review.router)
app.include_router(data_collection.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(ai.router)
app.include_router(files.router)
app.include_router(sop.router)
app.include_router(logs.router)
app.include_router(api_operation.router)
app.include_router(ai_chat.router)
app.include_router(hotspot.router)
app.include_router(market.router)
app.include_router(backtest.router)
app.include_router(feishu.router)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail.get("message") or "请求失败") if isinstance(exc.detail, dict) else "请求失败"
    error_code = exc.detail.get("error_code") if isinstance(exc.detail, dict) else f"HTTP_{exc.status_code}"
    stage = exc.detail.get("stage") if isinstance(exc.detail, dict) else ""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "ok": False,
            "error": detail,
            "message": detail,
            "detail": exc.detail,
            "error_code": error_code or f"HTTP_{exc.status_code}",
            "stage": stage,
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = uuid4().hex[:12]
    logger.exception("[request:%s] unhandled error path=%s", request_id, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "ok": False,
            "error_code": "INTERNAL_ERROR",
            "stage": "http:unhandled",
            "message": "服务端处理失败",
            "request_id": request_id,
        },
    )


def _page(request: Request, name: str) -> HTMLResponse:
    path = config.APP_DIR / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="页面不存在")
    return templates.TemplateResponse(name, {"request": request})


@app.get("/")
def root(request: Request) -> HTMLResponse:
    return _page(request, "index.html")


@app.get("/index.html")
def index(request: Request) -> HTMLResponse:
    return _page(request, "index.html")


# 下面这 4 个页面必须「真的返回页面」，不能做 302 跳转：
#   1) index.html 自己是用**带参数的链接**指向它们的（见 index.html:10694/10695/10706/10782/10906），
#      例如 /customer-list.html?anchor=X、/customer-profile.html?customer=X&anchor=Y；
#      RedirectResponse 用固定 URL，**会把查询参数整个丢掉**，跳过去页面就不知道要显示谁。
#   2) 其中三个的跳转目标分节（#sec-operation / #sec-customer-profile / #sec-customer-trends）
#      在 index.html 里**根本不存在**，浏览器忽略未知锚点 → 直接落回首页顶部。
#      这就是「点运营数据却回到首页」的原因。
# 等 index.html 里真的做出对应分节、且不再需要参数传递时，再改回 302 也不迟。
@app.get("/customer-list.html")
def customer_list(request: Request) -> HTMLResponse:
    return _page(request, "customer-list.html")


@app.get("/customer-profile.html")
def customer_profile(request: Request) -> HTMLResponse:
    return _page(request, "customer-profile.html")


@app.get("/customer-trends.html")
def customer_trends(request: Request) -> HTMLResponse:
    return _page(request, "customer-trends.html")


# /sop 与 /hotspot.html 保留 302：目标分节 #sec-sop、#sec-hotspot 在 index.html 里确实存在，
# 且这两个入口不需要传参数，跳转后行为正确。
@app.get("/sop")
def sop_page() -> RedirectResponse:
    return RedirectResponse(url="/index.html#sec-sop", status_code=302)


@app.get("/operation-dashboard.html")
def operation_dashboard(request: Request) -> HTMLResponse:
    return _page(request, "operation-dashboard.html")


@app.get("/hotspot.html")
def hotspot_page() -> RedirectResponse:
    return RedirectResponse(url="/index.html#sec-hotspot", status_code=302)


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.RELOAD,
        reload_excludes=[
            "**/__pycache__/**",
            "**/*.pyc",
            "**/.git/**",
            "**/.venv/**",
            "**/node_modules/**",
            "**/*.csv",
            "**/*.log",
        ],
        factory=False,
    )
