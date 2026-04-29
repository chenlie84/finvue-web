from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import config


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


def render_pdf_bytes(html: str, options: dict[str, Any] | None = None) -> bytes:
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


def render_pdf_file(html: str, file_name: str | None = None) -> dict[str, Any]:
    config.OBJECT_STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    base = safe_pdf_filename(file_name)
    target = config.OBJECT_STORAGE_DIR / f"{base}.pdf"
    counter = 1
    while target.exists():
        target = config.OBJECT_STORAGE_DIR / f"{base}-{counter}.pdf"
        counter += 1
    data = render_pdf_bytes(html)
    target.write_bytes(data)
    return {"fileName": target.name, "path": str(target), "bytes": len(data)}
