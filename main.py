"""FinVue FastAPI production entrypoint."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

import config
import migrate
from api import admin, ai, auth, customers, files, jobs, libraries, reports, settings, sop, system, logs, ai_chat, hotspot, market, backtest
from api import operation as api_operation


@asynccontextmanager
async def lifespan(_: FastAPI):
    hotspot_stop_event: asyncio.Event | None = None
    hotspot_task: asyncio.Task | None = None
    market_stop_event: asyncio.Event | None = None
    market_task: asyncio.Task | None = None
    print(f"[lifespan] AUTO_MIGRATE={config.AUTO_MIGRATE}, ENV={config.ENV}, has_mysql={config.has_mysql_config()}")
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


app = FastAPI(title="FinVue", version="2.0.0-fastapi", lifespan=lifespan)
templates = Jinja2Templates(directory=str(config.APP_DIR))

if config.STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")

app.include_router(system.router)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(jobs.router)
app.include_router(libraries.router)
app.include_router(customers.router)
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


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "error": detail, "detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc) or "服务端处理失败"})


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


@app.get("/customer-list.html")
def customer_list(request: Request) -> HTMLResponse:
    return _page(request, "customer-list.html")


@app.get("/customer-profile.html")
def customer_profile(request: Request) -> HTMLResponse:
    return _page(request, "customer-profile.html")


@app.get("/customer-trends.html")
def customer_trends(request: Request) -> HTMLResponse:
    return _page(request, "customer-trends.html")


@app.get("/sop")
def sop_page(request: Request) -> HTMLResponse:
    return _page(request, "sop.html")


@app.get("/operation-dashboard.html")
def operation_dashboard(request: Request) -> HTMLResponse:
    return _page(request, "operation-dashboard.html")


@app.get("/hotspot.html")
def hotspot_page(request: Request) -> HTMLResponse:
    return _page(request, "hotspot.html")


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.RELOAD,
        factory=False,
    )
