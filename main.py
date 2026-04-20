from pathlib import Path
from datetime import date
from typing import Optional

from fastapi import FastAPI, Query, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from db_utils import fetch_customer_activity
from pages.registry import PageRegistry
import db_sop


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
    from datetime import datetime
    for row in rows:
        if "dt" in row and isinstance(row["dt"], datetime):
            row["dt"] = row["dt"].strftime("%Y-%m-%d %H:%M:%S")
    return {"data": rows}


# ============================================================
# SOP 执行台 API
# ============================================================

class AnchorUpsertRequest(BaseModel):
    operatorName: str = Field(..., min_length=1, description="运营姓名")
    note: Optional[str] = None
    currentBlocker: Optional[str] = None


def _anchor_to_response(anchor_row: dict) -> dict:
    """把 DB 行转成前端响应，顺便计算 warning 派生字段。"""
    start_date = anchor_row["start_date"]
    today = date.today()
    days = (today - start_date).days + 1 if start_date else 0
    warning = days > 28

    return {
        "anchorName":     anchor_row["anchor_name"],
        "operatorName":   anchor_row["operator_name"],
        "startDate":      anchor_row["start_date"].isoformat() if anchor_row["start_date"] else None,
        "lastSavedDate":  anchor_row["last_saved_date"].isoformat() if anchor_row["last_saved_date"] else None,
        "currentWeek":    anchor_row["current_week"],
        "status":         anchor_row["status"],
        "note":           anchor_row["note"],
        "currentBlocker": anchor_row["current_blocker"],
        "warning":        warning,
    }


def _progress_to_response(row: dict) -> dict:
    return {
        "week":        row["week"],
        "actionIndex": row["action_index"],
        "subIndex":    row["sub_index"],
        "childIndex":  row["child_index"],
        "checked":     bool(row["checked"]),
        "note":        row["note"] or "",
    }


def _build_full_anchor(anchor_row: dict) -> dict:
    """构造一个带 progress 和 weekCompletions 的完整响应对象。"""
    resp = _anchor_to_response(anchor_row)
    name = anchor_row["anchor_name"]
    resp["progress"] = [_progress_to_response(r) for r in db_sop.list_progress(name)]
    resp["weekCompletions"] = {
        str(week): dt.isoformat() for week, dt in db_sop.list_week_completions(name).items()
    }
    return resp


@app.get("/api/sop/anchors")
async def api_list_anchors():
    anchors = db_sop.list_anchors()
    return {"anchors": [_build_full_anchor(a) for a in anchors]}


@app.get("/api/sop/anchors/{anchor_name}")
async def api_get_anchor(anchor_name: str):
    row = db_sop.get_anchor(anchor_name)
    if row is None:
        raise HTTPException(status_code=404, detail=f"anchor not found: {anchor_name}")
    return _build_full_anchor(row)


@app.put("/api/sop/anchors/{anchor_name}")
async def api_upsert_anchor(anchor_name: str, payload: AnchorUpsertRequest):
    db_sop.upsert_anchor(
        anchor_name=anchor_name,
        operator_name=payload.operatorName,
        note=payload.note,
        current_blocker=payload.currentBlocker,
    )
    row = db_sop.get_anchor(anchor_name)
    return _build_full_anchor(row)


@app.delete("/api/sop/anchors/{anchor_name}", status_code=204)
async def api_delete_anchor(anchor_name: str) -> None:
    if db_sop.get_anchor(anchor_name) is None:
        raise HTTPException(status_code=404, detail=f"anchor not found: {anchor_name}")
    db_sop.delete_anchor(anchor_name)


class ProgressUpsertRequest(BaseModel):
    week: int = Field(..., ge=1, le=4)
    actionIndex: int = Field(..., ge=0)
    subIndex: int = Field(-1, ge=-1)
    childIndex: int = Field(-1, ge=-1)
    checked: Optional[bool] = None
    note: Optional[str] = None


@app.put("/api/sop/anchors/{anchor_name}/progress", status_code=204)
async def api_upsert_progress(anchor_name: str, payload: ProgressUpsertRequest) -> None:
    if db_sop.get_anchor(anchor_name) is None:
        raise HTTPException(status_code=404, detail=f"anchor not found: {anchor_name}")
    db_sop.upsert_progress(
        anchor_name=anchor_name,
        week=payload.week,
        action_index=payload.actionIndex,
        sub_index=payload.subIndex,
        child_index=payload.childIndex,
        checked=payload.checked,
        note=payload.note,
    )


@app.post("/api/sop/anchors/{anchor_name}/advance")
async def api_advance_week(anchor_name: str):
    if db_sop.get_anchor(anchor_name) is None:
        raise HTTPException(status_code=404, detail=f"anchor not found: {anchor_name}")
    db_sop.advance_week(anchor_name)
    row = db_sop.get_anchor(anchor_name)
    return _build_full_anchor(row)


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
