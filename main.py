"""FinVue FastAPI production entrypoint."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

import config
import migrate
from api import admin, ai, auth, customers, jobs, libraries, reports, settings, sop, system


@asynccontextmanager
async def lifespan(_: FastAPI):
    if config.AUTO_MIGRATE and config.has_mysql_config() and config.ENV.lower() != "test":
        migrate.run_migrations()
    config.OBJECT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    yield


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
app.include_router(sop.router)


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
