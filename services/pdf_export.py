from __future__ import annotations

import re
import threading
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import config
from services import object_storage

_PDF_RENDER_LOCK = threading.Lock()


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
    root = Path(__file__).resolve().parent.parent

    def replace_link(match: re.Match[str]) -> str:
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
        replace_link,
        str(html or ""),
        flags=re.I,
    )


def _prepare_print_html(html: str) -> str:
    prepared = _inline_local_stylesheets(str(html or ""))
    print_css = """
<style id="finvue-pdf-print-style">
  @page { size: A4; margin: 12mm; }
  html, body { height: auto !important; overflow: visible !important; }
  * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
  .panel-act, button, input, textarea, select { display: none !important; }
  .live-result-wrap, .live-result-shell, .report-page, .report-section {
    break-inside: avoid-page;
    page-break-inside: avoid;
  }
  table, pre, blockquote {
    break-inside: avoid-page;
    page-break-inside: avoid;
  }
</style>
"""
    if "</head>" in prepared.lower():
        return re.sub(r"</head>", f"{print_css}\n</head>", prepared, count=1, flags=re.I)
    return f"<!doctype html><html><head><meta charset=\"utf-8\">{print_css}</head><body>{prepared}</body></html>"


def _render_pdf_bytes_browser(html: str, options: dict[str, Any] | None = None) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on deployment package
        raise RuntimeError("浏览器 PDF 渲染组件未安装，请先安装 playwright，并执行 playwright install chromium") from exc

    prepared_html = _prepare_print_html(html)
    timeout_ms = int((options or {}).get("timeoutMs") or 45000)
    with _PDF_RENDER_LOCK:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            try:
                page = browser.new_page(viewport={"width": 960, "height": 1280})
                page.set_default_timeout(timeout_ms)
                page.set_content(prepared_html, wait_until="networkidle", timeout=timeout_ms)
                page.emulate_media(media="print")
                return page.pdf(
                    format=str((options or {}).get("format") or "A4"),
                    print_background=True,
                    prefer_css_page_size=True,
                    margin={
                        "top": str((options or {}).get("marginTop") or "12mm"),
                        "right": str((options or {}).get("marginRight") or "12mm"),
                        "bottom": str((options or {}).get("marginBottom") or "12mm"),
                        "left": str((options or {}).get("marginLeft") or "12mm"),
                    },
                )
            finally:
                browser.close()


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
    engine = str((options or {}).get("engine") or "browser").strip().lower()
    if engine in {"text", "reportlab"}:
        return _render_pdf_bytes_text(html)
    return _render_pdf_bytes_browser(html, options)


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
