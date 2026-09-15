#!/usr/bin/env python3
"""从主播资料库已有的 HTML 报告里回填结构化字段。

背景：早期保存主播档案时只存了 markdown 报告原文，contentSchool / complianceLevel /
coreSummary / tags / scores / evidence 这些结构化字段全是空的，导致资料库页面出现大量
「未识别 / 暂无 / —」占位。但报告正文里其实写着合规总评级、人设一句话、互动指标等。

本脚本用正则从报告里把这些内容挖出来，回填到对应字段。不调用 AI，纯解析。

用法：
    python3 scripts/backfill_anchor_profiles.py            # dry-run，只打印不写库
    python3 scripts/backfill_anchor_profiles.py --apply    # 真正写库
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from typing import Any

BASE_URL = "http://localhost:8080"
SESSION_COOKIE = ""  # 通过 --cookie 传入，或设环境变量 FINVUE_SESSION


# ── HTML 预处理 ────────────────────────────────────────────────────────────

def unwrap_report(markdown: str) -> str:
    """去掉 ```html 代码围栏，剥掉 style/script，返回正文 HTML。"""
    if not markdown:
        return ""
    m = re.search(r"```(?:html)?\s*\n(.*?)(?:```)?\s*$", markdown, re.DOTALL)
    inner = m.group(1) if m else markdown
    inner = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", inner, flags=re.DOTALL | re.I)
    return inner


def strip_tags(fragment: str) -> str:
    """去掉 HTML 标签并把实体还原成字符，压缩空白。"""
    text = re.sub(r"<[^>]+>", "", fragment or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def split_sections(inner: str) -> dict[str, str]:
    """按 h2 切分成 {章节关键词: 章节 HTML}。

    h2 里带序号徽章，形如 <h2><span class="tag-red">03</span> 合规总评级</h2>，
    所以先剥标签再取标题，然后按关键词建索引方便模糊匹配。
    """
    marks = [m for m in re.finditer(r"<h2[^>]*>(.*?)</h2>", inner, re.DOTALL | re.I)]
    sections: dict[str, str] = {}
    for i, m in enumerate(marks):
        title = strip_tags(m.group(1))
        end = marks[i + 1].start() if i + 1 < len(marks) else len(inner)
        body = inner[m.end():end]
        if title:
            sections[title] = body
    return sections


def find_section(sections: dict[str, str], keyword: str) -> str:
    """按关键词模糊找章节，返回章节 HTML（找不到返回空串）。"""
    for title, body in sections.items():
        if keyword in title:
            return body
    return ""


def first_table_rows(section_html: str) -> list[list[str]]:
    """取章节里第一张表格的所有数据行，每行的单元格文本组成列表。"""
    m = re.search(r"<table[^>]*>(.*?)</table>", section_html, re.DOTALL | re.I)
    if not m:
        return []
    rows: list[list[str]] = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(1), re.DOTALL | re.I):
        if "<th" in tr.lower():
            continue
        cells = [strip_tags(td) for td in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL | re.I)]
        if cells:
            rows.append(cells)
    return rows


def lead_text(section_html: str) -> str:
    """取章节里第一段引导文案。

    AI 每次生成的类名都不一样（lead / conclusion / quote / summary），
    所以按常见类名依次试探，全都落空就退化成取第一段 <p>/<div> 文本。
    """
    for pattern in (
        r'<div class="lead[^"]*">(.*?)</div>',
        r'<div class="conclusion[^"]*">(.*?)</div>',
        r'<div class="verdict[^"]*">(.*?)</div>',
        r'<blockquote[^>]*>(.*?)</blockquote>',
        r'<div class="summary[^"]*">(.*?)</div>',
    ):
        m = re.search(pattern, section_html, re.DOTALL | re.I)
        if m:
            text = strip_tags(m.group(1))
            if text:
                return text
    m = re.search(r"<p[^>]*>(.*?)</p>", section_html, re.DOTALL | re.I)
    return strip_tags(m.group(1)) if m else ""


# 指标名 → 数值形态。AI 生成的类名不固定，但指标名和量纲是稳定的，
# 所以直接对纯文本做模式匹配，比按 class 抓靠谱得多。
# 数值形态：01:25 / 1'35" / 约8次 / 约4.5分钟 / 2分48秒
_NUM = (
    r"(?:约\s*)?(?:\d{1,3}\s*[:'’]\s*\d{2}\s*[\"”″]?"
    r"|\d+(?:\.\d+)?\s*(?:分\s*\d+\s*秒|分钟|秒钟|秒|分|次))"
)
# 标签名各家写法不同：首次有效互动 / 首次正式互动；前15分钟互动次数 / 前15分钟互动；
# 最长干货段 / 最长无互动干货段 / 全场最长干货段 / 前15分钟最长干货段
_METRIC_LABELS: dict[str, str] = {
    "首次有效互动": r"首次(?:有效|正式)互动",
    "前15分钟互动次数": r"前\s*15\s*分钟互动(?:次数)?",
    "最长干货段": r"(?:全场|前\s*15\s*分钟)?最长(?:无互动)?干货段",
}
METRIC_PATTERNS: list[tuple[str, str]] = [
    ("首次有效互动", _NUM),
    ("前15分钟互动次数", _NUM),
    ("最长干货段", _NUM),
]

# 标签和它的值之间最多能隔几个字符。真正的指标卡里两者紧挨着（剥掉标签后
# 只剩一个空格），而散文里的同名词汇后面往往跟一大串话。价值探路_20260622 的
# 结论句「前15分钟互动偏弱…且存在7分钟」间隔 23 个字符，靠这个上限挡掉。
_GAP_MAX = 4


def _nearest_value(text: str, label_re: str, num_re: str) -> str:
    """在文本里找离指标名最近的那个数值。

    数值可能在名字前面（`1'35"首次有效互动`）也可能在后面（`首次有效互动 01:25`），
    两种都试，取间隔最短的那个。这很关键——比如满仓红那段「首次有效互动达标，
    小于3分钟」，名字后面既跟着干扰文案又跟着一个 3 分钟，但真正的 1'35" 就在
    名字前面、间隔为零，按最小间隔取就能选对。

    实现上必须先把「指标名出现的每个位置」和「每个数值」分别找出来，再两两配对。
    不能直接用 `re.finditer('指标名.*?数值')` 一把梭——那样第一个匹配可能横跨
    很长的干扰文字，把后面真正紧邻的那对给吞掉。价值探路_20260622 就栽在这：
    结论句里的「前15分钟互动偏弱…存在7分钟无互动长干货段」先匹配上了，于是
    表格里的「前15分钟互动次数3次」反而被跳过。

    间隔相同时优先「数值在前」那一侧。旗帜鲜明那份就靠这条：文字是
    「约 2分48秒 最长干货段 07:03 到 09:51」，名字两侧各有一个数值、间隔都是
    一个空格，但真正的指标值是前面的时长，后面的 07:03 只是备注里的起始时刻。
    """
    return _nearest_pair(text, label_re, num_re)[1]


def _nearest_pair(text: str, label_re: str, num_re: str) -> tuple[tuple[int, int], str]:
    """同 _nearest_value，但把排序键一并返回，方便跨区域比较优劣。"""
    label_spans = list(re.finditer(rf"(?:{label_re})", text))
    num_spans = list(re.finditer(rf"(?:{num_re})", text))
    if not label_spans or not num_spans:
        return ((999, 9), "")

    best: tuple[tuple[int, int], str] | None = None

    def offer(gap: str, priority: int, raw: str) -> None:
        nonlocal best
        key = (len(gap), priority)
        value = re.sub(r"\s+", "", raw)
        if best is None or key < best[0]:
            best = (key, value)

    for ls in label_spans:
        # 数值在指标名右边
        for ns in num_spans:
            if ns.start() < ls.end():
                continue
            gap = text[ls.end():ns.start()]
            if len(gap) > _GAP_MAX or re.search(r"[0-9约]", gap):
                break  # 右边第一个数值就超距，后面的只会更远
            offer(gap, 1, ns.group(0))
            break
        # 数值在指标名左边
        left = [ns for ns in num_spans if ns.end() <= ls.start()]
        if left:
            ns = left[-1]
            gap = text[ns.end():ls.start()]
            if len(gap) <= _GAP_MAX and not re.search(r"[0-9]", gap):
                offer(gap, 0, ns.group(0))

    return best if best else ((999, 9), "")


def metric_cards(section_html: str) -> list[dict[str, str]]:
    """从「关键互动指标」章节里抓三项核心指标。

    各家报告的结构完全不一样，别去猜 HTML：
    - 丹哥是两个相邻 div，label 在前 value 在后
    - 满仓红是 num 在前 lab 在后，而且 class 是「num green」这种复合类名
    - 旗帜鲜明是数值和名字塞在同一个 div 里，名字放在 <small> 里
    - 价值探路_20260622 压根没有指标卡，数字只在表格里；而表格前的结论句
      「前15分钟互动偏弱…存在7分钟无互动」是个陷阱，只扫前半段就会取错

    所以统一走纯文本 + 最小间隔匹配（见 _nearest_value）。**优先只扫指标卡区**
    （第一个 <table> 之前）：那里给的是本场实测值，而表格里是「现状 vs 参考线」
    两列对照，同名指标会连带出现参考线数字。卡的区扫不到，才退回整个章节。
    配合 _GAP_MAX 把散文里的同名词汇过滤掉，两个机制一起才能同时搞定
    价值探路_20260622（只有表格有数）和股的morning（表格里有干扰参考线）。
    """
    table_pos = section_html.lower().find("<table")
    card_text = strip_tags(section_html[:table_pos]) if table_pos > 0 else ""
    full_text = strip_tags(section_html)

    cards: list[dict[str, str]] = []
    for label, num_re in METRIC_PATTERNS:
        label_re = _METRIC_LABELS[label]
        best: tuple[tuple[int, int], str] | None = None
        for area in (card_text, full_text):
            if not area:
                continue
            candidate = _nearest_pair(area, label_re, num_re)
            if candidate[1] and (best is None or candidate[0] < best[0]):
                best = candidate
            # 指标卡区命中就不再看全文，避免被表格里的参考线数字带偏
            if best and best[1] and area is card_text:
                break
        if best and best[1]:
            cards.append({"label": label, "value": best[1], "note": ""})
    return cards


# ── 字段提取 ──────────────────────────────────────────────────────────────

def extract_persona(sections: dict[str, str]) -> str:
    """「主播人设一句话」→ coreSummary。

    优先从「人设一句话：」这个固定前缀后面截正文；标记可能在 <strong> 里，
    所以要先剥标签再找，最后截到句号为止。
    """
    body = find_section(sections, "人设一句话")
    if not body:
        return ""
    m = re.search(r"人设一句话\s*[:：]\s*(.{10,300}?)(?=(?:后面|后续|本文|所有)|$)", strip_tags(body), re.DOTALL)
    text = m.group(1).strip() if m else lead_text(body)
    text = re.sub(r"^[^：:]{0,10}[：:]\s*", "", text).strip()
    # 只保留第一句
    m = re.search(r"^(.{10,200}?[。！？])", text)
    return (m.group(1) if m else text[:160]).strip()


def extract_compliance(sections: dict[str, str]) -> dict[str, str]:
    """03 合规总评级 → complianceLevel + 一句话结论 + 主要依据。"""
    rows = first_table_rows(find_section(sections, "合规总评级"))
    if not rows:
        # 退化：从 01 管理层摘要卡的「合规评级」行取
        for row in first_table_rows(find_section(sections, "管理层摘要卡")):
            if row and row[0].strip() == "合规评级" and len(row) > 1:
                return {"level": row[1].strip(), "conclusion": "", "basis": ""}
        return {"level": "", "conclusion": "", "basis": ""}
    row = rows[0]
    return {
        "level": row[0].strip() if len(row) > 0 else "",
        "conclusion": row[1].strip() if len(row) > 1 else "",
        "basis": row[2].strip() if len(row) > 2 else "",
    }


def extract_evidence(sections: dict[str, str]) -> list[str]:
    """合规风险清单 → evidence.compliance（风险点 + 等级 + 原话）。

    两种模板的章节名不同：模板 A 叫「合规风险明细」，模板 B 叫「合规风险清单」。
    """
    body = find_section(sections, "合规风险明细") or find_section(sections, "合规风险清单")
    lines: list[str] = []
    for row in first_table_rows(body)[:6]:
        if len(row) < 2:
            continue
        point = row[0].strip()
        quote = row[1].strip()
        level = row[2].strip() if len(row) > 2 else ""
        piece = f"[{level}] {point}" if level else point
        if quote:
            piece += f"：{quote[:60]}{'…' if len(quote) > 60 else ''}"
        lines.append(piece)
    return lines


def extract_metrics(sections: dict[str, str]) -> list[dict[str, str]]:
    """04 关键互动指标 → 指标卡（首次有效互动 / 前15分钟互动次数 / 最长无互动段）。"""
    return metric_cards(find_section(sections, "关键互动指标"))


# ── 模板 B：结构化标签字典 ─────────────────────────────────────────────────
# 章节形如：◆第一输出层 / ◆四维诊断速览 / 1.主播画像归类 / 2.六维评分总表 /
#          3.关键证据摘录 / 4.合规风险清单 / 5.结构与节奏分析 ...
# 这一版反而有真正的流派标签、风格标签和六维分数。

SCHOOL_KEYS = ("实战派", "研究派", "消息派", "陪伴派")


def extract_school(sections: dict[str, str]) -> str:
    """1.主播画像归类 → contentSchool（四选一主流派）。"""
    body = find_section(sections, "画像归类")
    if not body:
        return ""
    for key in SCHOOL_KEYS:
        if key in body:
            # 流派后面常跟括号说明，如「实战派（交易员/复盘型）」，右括号要一并带上
            m = re.search(rf"({key}\s*(?:[（(][^）)]{{0,16}}[）)])?)", strip_tags(body))
            return m.group(1).strip() if m else key
    return ""


def extract_style_tags(sections: dict[str, str]) -> list[str]:
    """1.主播画像归类里的 chip 风格标签。"""
    body = find_section(sections, "画像归类")
    if not body:
        return []
    tags = [strip_tags(t) for t in re.findall(r'<span class="chip[^"]*"[^>]*>(.*?)</span>', body, re.DOTALL | re.I)]
    return [t for t in tags if t][:8]


SIX_DIM_KEYS = ("内容专业度", "合规安全", "结构节奏", "表达呈现", "互动承接", "转化效率")


def extract_scores(sections: dict[str, str]) -> dict[str, str]:
    """2.六维评分总表 → scores。只认表格里的「维度 + 分数」两列。"""
    scores: dict[str, str] = {}
    field_map = {
        "内容专业度": "professional",
        "合规安全": "compliance",
        "结构节奏": "structure",
        "表达呈现": "delivery",
        "互动承接": "interaction",
        "转化效率": "conversion",
    }
    for row in first_table_rows(find_section(sections, "六维评分")):
        if len(row) < 2:
            continue
        dim, val = row[0].strip(), row[1].strip()
        m = re.search(r"(\d+(?:\.\d+)?)", val)
        if not m:
            continue
        for cn, en in field_map.items():
            if cn in dim:
                scores[en] = m.group(1)
                break
    return scores


def extract_diagnosis(sections: dict[str, str]) -> str:
    """◆四维诊断速览 → coreSummary（取合规风控那一段）。"""
    body = find_section(sections, "四维诊断")
    if not body:
        return ""
    for block in re.findall(r'<div class="tag-item">(.*?)</div>\s*</div>', body, re.DOTALL | re.I):
        label = re.search(r'<div class="label"[^>]*>(.*?)</div>', block, re.DOTALL | re.I)
        para = re.search(r"<p[^>]*>(.*?)</p>", block, re.DOTALL | re.I)
        if label and para and "合规" in strip_tags(label.group(1)):
            return strip_tags(para.group(1))
    return ""


def extract_tags(compliance_level: str, metrics: list[dict[str, str]], sections: dict[str, str]) -> list[str]:
    """生成标签。模板 B 有现成的风格标签，优先用；否则用合规等级 + 互动指标拼。"""
    style_tags = extract_style_tags(sections)
    tags: list[str] = []
    if compliance_level:
        tags.append(f"合规·{compliance_level}")
    if style_tags:
        tags.extend(style_tags)
    else:
        for card in metrics[:3]:
            if card["label"] and card["value"]:
                tags.append(f"{card['label']} {card['value']}")
    # 去重保序
    seen, out = set(), []
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out[:8]


def build_patch(profile: dict[str, Any]) -> dict[str, Any]:
    """从一份档案的报告里提取所有可回填字段。"""
    # 优先用最新快照的报告，没有则退回档案自带的 markdown
    snapshots = [s for s in (profile.get("snapshots") or []) if isinstance(s, dict)]
    snapshots.sort(key=lambda s: str(s.get("analyzedAt") or ""), reverse=True)
    report_md = ""
    for snap in snapshots:
        if snap.get("markdown"):
            report_md = snap["markdown"]
            break
    report_md = report_md or profile.get("markdown") or ""

    inner = unwrap_report(report_md)
    if not inner:
        return {}

    sections = split_sections(inner)
    # 模板 B（结构化标签字典）有独立章节名，用「六维评分」是否存在来判定
    is_dict_template = bool(find_section(sections, "六维评分"))

    compliance = extract_compliance(sections)
    if not compliance["level"] and is_dict_template:
        # 模板 B 没有评级总表，从四维诊断的文字里找「灰区 / 高危 / 安全」这类判断
        diag = extract_diagnosis(sections)
        m = re.search(r"(高危|红线|灰区|安全|可控)", diag)
        if m:
            compliance["level"] = m.group(1)

    metrics = extract_metrics(sections)
    evidence = extract_evidence(sections)
    persona = extract_persona(sections) or (extract_diagnosis(sections) if is_dict_template else "")

    patch: dict[str, Any] = {}
    if persona:
        patch["coreSummary"] = persona
    if compliance["level"]:
        patch["complianceLevel"] = compliance["level"]
    if compliance["basis"]:
        patch["complianceBasis"] = compliance["basis"]
    if metrics:
        patch["liveMetrics"] = metrics
    if evidence:
        patch["evidence"] = {**(profile.get("evidence") or {}), "compliance": evidence}

    if is_dict_template:
        school = extract_school(sections)
        if school:
            patch["contentSchool"] = school
        scores = extract_scores(sections)
        if scores:
            patch["scores"] = scores

    tags = extract_tags(compliance["level"], metrics, sections)
    if tags:
        patch["tags"] = tags

    patch["_debug"] = {
        "template": "标签字典" if is_dict_template else "运营诊断",
        "sections": len(sections),
        "reportChars": len(inner),
        "complianceConclusion": compliance["conclusion"],
    }
    return patch


# ── 网络 ──────────────────────────────────────────────────────────────────

def fetch_profiles(cookie: str) -> list[dict[str, Any]]:
    req = urllib.request.Request(
        f"{BASE_URL}/api/anchor-profiles",
        headers={"Cookie": f"lab_session={cookie}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("items") or data.get("profiles") or []


def push_profile(cookie: str, profile_id: str, patch: dict[str, Any]) -> bool:
    """单条 upsert。注意：必须走 {profile: {...}} 单条模式，
    {profiles: [...]} 批量模式会先 DELETE 全表再重建。"""
    body = json.dumps({"profile": {"id": profile_id, **patch}}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}/api/anchor-profiles",
        data=body,
        headers={"Content-Type": "application/json", "Cookie": f"lab_session={cookie}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()
    return True


def main() -> int:
    global BASE_URL
    parser = argparse.ArgumentParser(description="从已有报告回填主播资料库结构化字段")
    parser.add_argument("--apply", action="store_true", help="真正写库（默认只 dry-run）")
    parser.add_argument("--cookie", default=SESSION_COOKIE, help="lab_session cookie 值")
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()

    BASE_URL = args.base_url.rstrip("/")

    cookie = args.cookie or __import__("os").environ.get("FINVUE_SESSION", "")
    if not cookie:
        print("缺少会话 cookie：用 --cookie <value> 或设环境变量 FINVUE_SESSION", file=sys.stderr)
        return 2

    profiles = fetch_profiles(cookie)
    print(f"读到 {len(profiles)} 份档案\n")

    ok = skipped = 0
    for profile in profiles:
        name = profile.get("anchorName") or profile.get("id") or "?"
        patch = build_patch(profile)
        debug = patch.pop("_debug", {})
        if not patch:
            print(f"[跳过] {name} — 报告为空或无法解析（章节数 {debug.get('sections', 0)}）")
            skipped += 1
            continue

        print(f"[{'写入' if args.apply else '预演'}] {name}")
        print(f"        章节 {debug.get('sections')} 个 / 报告 {debug.get('reportChars')} 字符")
        for key in ("complianceLevel", "contentSchool", "coreSummary", "scores", "liveMetrics", "tags", "evidence"):
            if key in patch:
                val = patch[key]
                shown = json.dumps(val, ensure_ascii=False)
                print(f"        {key}: {shown[:110]}{'…' if len(shown) > 110 else ''}")
        if args.apply:
            push_profile(cookie, profile["id"], patch)
        print()

    print(f"完成：{ok if args.apply else len(profiles) - skipped} 份待写入 / {skipped} 份跳过")
    if not args.apply:
        print("（dry-run 未写库，加 --apply 真正执行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
