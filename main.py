from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pages.registry import PageRegistry


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

