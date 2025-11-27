from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from db_utils import fetch_all_rows


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
    rows = fetch_all_rows()
    title = "CRS填写客户数"
    cutoff_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return templates.TemplateResponse(
        "report.html",
        {
            "request": request,
            "title": title,
            "rows": rows,
            "cutoff_time": cutoff_time,
        },
    )


def get_app() -> FastAPI:
    return app


if __name__ == "__main__":
    import uvicorn
    import threading
    import time
    from capture_screenshot import capture

    # 启动服务器的函数
    def run_server():
        uvicorn.run("main:app", host="127.0.0.1", port=8000, log_level="error")

    # 在后台线程启动服务器
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # 等待服务器启动
    print("正在启动服务器...")
    time.sleep(3)

    try:
        # 截图
        print("正在截取网页...")
        screenshot_path = capture(
            url="http://127.0.0.1:8000/",
            output_path="output/crs_screenshot.png",
            window_width=1100,
            window_height=768,
        )
        print(f"截图已保存到: {screenshot_path}")
    except Exception as e:
        print(f"截图失败: {e}")
    finally:
        print("完成，正在关闭...")

