from __future__ import annotations

import re
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import config
from services import object_storage


def safe_pdf_filename(value: str | None) -> str:
    name = str(value or "finvue-report").strip()
    name = re.sub(r"[\\/:*?\"<>|\r\n]+", "-", name).strip(" .-")
    name = re.sub(r"\.pdf$", "", name, flags=re.I).strip(" .-")
    return (name or "finvue-report")[:120]


class _HtmlTextParser(HTMLParser):
    block_tags = {"p", "div", "section", "article", "header", "footer", "br", "li", "tr", "table", "h1", "h2", "h3", "h4", "h5"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.skip_depth += 1
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"} and self.skip_depth:
            self.skip_depth -= 1
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = re.sub(r"\s+", " ", data or "").strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        raw = "\n".join(self.parts)
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    parser = _HtmlTextParser()
    parser.feed(str(html or ""))
    text = parser.text()
    return text or re.sub(r"<[^>]+>", "", str(html or "")).strip()


def _wrap_cjk_line(text: str, max_chars: int = 38) -> list[str]:
    line = str(text or "").strip()
    if not line:
        return [""]
    return [line[index : index + max_chars] for index in range(0, len(line), max_chars)]


def _inline_local_stylesheets(html: str) -> str:
    """Inline root-relative app styles so file:// rendering keeps the report shape."""
    root = Path(__file__).resolve().parent.parent

    def _replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        href_match = re.search(r'href=["\']([^"\']+)["\']', tag, flags=re.I)
        if not href_match:
            return tag
        href = href_match.group(1).split("?", 1)[0]
        if not href.startswith("/static/"):
            return tag
        path = root / "app" / href.lstrip("/")
        try:
            css = path.read_text(encoding="utf-8")
        except Exception:
            return tag
        return f"<style>\n{css}\n</style>"

    return re.sub(
        r"<link\b(?=[^>]*rel=[\"']stylesheet[\"'])[^>]*>",
        _replace,
        str(html or ""),
        flags=re.I,
    )


def _render_pdf_bytes_screenshot(html: str, options: dict[str, Any] | None = None) -> bytes:
    try:
        from io import BytesIO

        from PIL import Image
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on deployment package
        raise RuntimeError("高清 PDF 渲染组件未安装，请先安装 playwright、Pillow，并执行 playwright install chromium") from exc

    viewport_width = int((options or {}).get("viewportWidth") or 1200)
    viewport_height = int((options or {}).get("viewportHeight") or 900)
    scale = float((options or {}).get("scale") or 2.0)
    prepared_html = _inline_local_stylesheets(str(html or ""))

    with tempfile.TemporaryDirectory(prefix="finvue-pdf-") as tmpdir:
        html_path = Path(tmpdir) / "report.html"
        html_path.write_text(prepared_html, encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page(
                    viewport={"width": viewport_width, "height": viewport_height},
                    device_scale_factor=scale,
                )
                page.goto(html_path.as_uri(), wait_until="networkidle")
                page.emulate_media(media="screen")
                page.add_style_tag(content="""
                  html, body { height: auto !important; overflow: visible !important; }
                  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
                """)
                screenshot = page.screenshot(full_page=True, type="png", animations="disabled")
            finally:
                browser.close()

    image = Image.open(BytesIO(screenshot))
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[3])
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    output = BytesIO()
    image.save(output, "PDF", dpi=(300, 300), resolution=300)
    return output.getvalue()


def _render_pdf_bytes_text(html: str) -> bytes:
    if not str(html or "").strip():
        raise RuntimeError("缺少 HTML 内容，无法生成 PDF")
    try:
        from io import BytesIO

        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfbase import pdfmetrics
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except Exception as exc:  # pragma: no cover - depends on deployment package
        raise RuntimeError("PDF 渲染组件未安装，请先执行：pip install -r requirements.txt") from exc

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "FinVueBody",
        parent=styles["Normal"],
        fontName="STSong-Light",
        fontSize=10.5,
        leading=17,
        textColor=colors.HexColor("#222222"),
        spaceAfter=5,
    )
    title = ParagraphStyle(
        "FinVueTitle",
        parent=body,
        fontSize=18,
        leading=24,
        textColor=colors.HexColor("#111111"),
        spaceAfter=10,
    )
    accent = ParagraphStyle(
        "FinVueAccent",
        parent=body,
        fontSize=12,
        leading=19,
        textColor=colors.HexColor("#9a6a00"),
        spaceBefore=6,
        spaceAfter=6,
    )
    story = []
    for index, raw_line in enumerate(html_to_text(html).splitlines()):
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue
        style = title if index == 0 or len(line) <= 24 and ("报告" in line or "总结" in line) else accent if re.match(r"^[一二三四五六七八九十\d]+[、.．]|^#+|^第.+", line) else body
        for chunk in _wrap_cjk_line(line):
            story.append(Paragraph(chunk.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style))
    doc.build(story)
    return buffer.getvalue()


def render_pdf_bytes(html: str, options: dict[str, Any] | None = None) -> bytes:
    if not str(html or "").strip():
        raise RuntimeError("缺少 HTML 内容，无法生成 PDF")
    engine = str((options or {}).get("engine") or "screenshot").strip().lower()
    if engine in {"text", "reportlab"}:
        return _render_pdf_bytes_text(html)
    return _render_pdf_bytes_screenshot(html, options)


def render_pdf_file(html: str, file_name: str | None = None) -> dict[str, Any]:
    base = safe_pdf_filename(file_name)
    data = render_pdf_bytes(html)
    file_name = f"{base}.pdf"
    if config.has_ceph_config():
        result = object_storage.upload_bytes(data, file_name=file_name, prefix=config.CEPH_KEY_PREFIX, content_type="application/pdf")
        return {"fileName": file_name, "bytes": len(data), "storage": "ceph", **result}

    # Local fallback is only for development or when Ceph is explicitly disabled.
    config.OBJECT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = config.OBJECT_STORAGE_DIR / file_name
    counter = 1
    while target.exists():
        target = config.OBJECT_STORAGE_DIR / f"{base}-{counter}.pdf"
        counter += 1
    target.write_bytes(data)
    return {"fileName": target.name, "path": str(target), "bytes": len(data), "storage": "local"}
