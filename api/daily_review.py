from __future__ import annotations

import re
import subprocess
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse

import config
import security
import store
from services import tushare_market


router = APIRouter()
_REPORT_NAME_RE = re.compile(r"^a_share_daily_review_(\d{8})\.html$")


def _review_permission():
    return security.require_any_permission("research", "market", "export")


def _output_dir() -> Path:
    return Path(config.DAILY_MARKET_REVIEW_OUTPUT_DIR).expanduser().resolve()


def _data_dir() -> Path:
    return Path(config.DAILY_MARKET_REVIEW_ROOT).expanduser().resolve() / "data" / "daily-market-review"


def _script_path() -> Path | None:
    raw = store.text(config.DAILY_MARKET_REVIEW_SCRIPT)
    return Path(raw).expanduser().resolve() if raw else None


def _normalize_trade_date(value: Any) -> str:
    text = store.text(value).replace("-", "")
    if text and not re.match(r"^\d{8}$", text):
        raise HTTPException(status_code=400, detail="交易日期格式应为 YYYYMMDD")
    return text


def _filename_for_upload(original_name: str, trade_date: str) -> str:
    name = Path(store.text(original_name)).name
    matched = _REPORT_NAME_RE.match(name)
    if matched and (not trade_date or matched.group(1) == trade_date):
        return name
    if not trade_date:
        date_match = re.search(r"(20\d{6})", name)
        if date_match:
            trade_date = date_match.group(1)
    if not trade_date:
        raise HTTPException(status_code=400, detail="请指定交易日期，或上传 a_share_daily_review_YYYYMMDD.html 格式文件")
    return f"a_share_daily_review_{trade_date}.html"


def _safe_report_path(filename: str) -> Path:
    name = Path(store.text(filename)).name
    if not _REPORT_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="复盘报告文件名不合法")
    base = _output_dir()
    path = (base / name).resolve()
    if base not in path.parents and path != base:
        raise HTTPException(status_code=400, detail="复盘报告路径不合法")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="复盘报告不存在")
    return path


def _report_meta(path: Path) -> dict[str, Any]:
    matched = _REPORT_NAME_RE.match(path.name)
    trade_date = matched.group(1) if matched else ""
    stat = path.stat()
    updated = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    title_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:]}" if trade_date else path.stem
    return {
        "filename": path.name,
        "tradeDate": trade_date,
        "title": f"A股每日行情复盘 · {title_date}",
        "updatedAt": updated,
        "size": stat.st_size,
        "viewUrl": f"/api/daily-review/reports/{path.name}",
    }


def _reports() -> list[dict[str, Any]]:
    base = _output_dir()
    if not base.exists():
        return []
    paths = [path for path in base.glob("a_share_daily_review_*.html") if _REPORT_NAME_RE.match(path.name)]
    return [_report_meta(path) for path in sorted(paths, key=lambda item: item.name, reverse=True)]


@router.get("/api/daily-review/reports")
def list_daily_reviews(_: dict = Depends(_review_permission())) -> dict:
    reports = _reports()
    return {
        "ok": True,
        "reports": reports,
        "latest": reports[0] if reports else None,
        "outputDir": str(_output_dir()),
        "scriptConfigured": bool(_script_path() and _script_path().exists()),
    }


@router.get("/api/daily-review/reports/{filename}")
def get_daily_review_html(filename: str, _: dict = Depends(_review_permission())) -> HTMLResponse:
    path = _safe_report_path(filename)
    html = path.read_text(encoding="utf-8")
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/api/daily-review/generate")
async def generate_daily_review(request: Request, _: dict = Depends(_review_permission())) -> dict:
    body = await request.json()
    trade_date = _normalize_trade_date(body.get("date"))

    script = _script_path()
    if not script or not script.exists():
        raise HTTPException(status_code=404, detail="云端复盘生成脚本不存在，请检查 DAILY_MARKET_REVIEW_SCRIPT")
    tushare_settings = tushare_market.get_settings()
    token = store.text(tushare_settings.get("token"))
    if not token:
        raise HTTPException(status_code=400, detail="请先在管理后台配置 TuShare Token，再线上生成行情复盘")

    command = [sys.executable, str(script)]
    if trade_date:
        command.extend(["--date", trade_date])

    try:
        env = {
            **os.environ,
            "TUSHARE_TOKEN": token,
            "DAILY_MARKET_REVIEW_OUTPUT_DIR": str(_output_dir()),
            "DAILY_MARKET_REVIEW_DATA_DIR": str(_data_dir()),
        }
        result = subprocess.run(
            command,
            cwd=str(script.parent.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(status_code=504, detail="复盘生成超时，请稍后查看输出目录") from exc

    if result.returncode != 0:
        error = (result.stderr or result.stdout or "复盘生成失败").strip()
        raise HTTPException(status_code=500, detail=error[-1000:])

    reports = _reports()
    return {
        "ok": True,
        "message": "行情复盘已生成",
        "stdout": (result.stdout or "").strip()[-2000:],
        "latest": reports[0] if reports else None,
        "reports": reports,
    }


@router.post("/api/daily-review/upload")
async def upload_daily_review(
    file: UploadFile = File(...),
    date: str = Form(""),
    _: dict = Depends(_review_permission()),
) -> dict:
    trade_date = _normalize_trade_date(date)
    filename = _filename_for_upload(file.filename or "", trade_date)
    content = await file.read()
    if len(content) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="上传文件过大")
    try:
        html = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            html = content.decode("gb18030")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="HTML 文件编码无法识别，请使用 UTF-8") from exc
    if "<html" not in html.lower() or "</html>" not in html.lower():
        raise HTTPException(status_code=400, detail="请上传完整 HTML 复盘报告")

    base = _output_dir()
    base.mkdir(parents=True, exist_ok=True)
    path = (base / filename).resolve()
    if base not in path.parents:
        raise HTTPException(status_code=400, detail="上传路径不合法")
    path.write_text(html, encoding="utf-8")
    reports = _reports()
    current = _report_meta(path)
    return {
        "ok": True,
        "message": "行情复盘已上传到云端",
        "report": current,
        "latest": reports[0] if reports else current,
        "reports": reports,
    }
