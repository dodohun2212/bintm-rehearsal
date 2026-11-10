"""F08 문제 그림(트리·배열·표) 검사와 그리기, 페이지·그림을 가리키는 문제 찾기."""
from __future__ import annotations

import base64
import html
import re

MAX_TREE = 31
MAX_COLS = 6
MAX_ROWS = 10
MAX_ITEMS = 40

# 밝은·어두운 화면 모두에서 보이도록 고정 색
_FILL = "#ffffff"
_STROKE = "#2563eb"
_TEXT = "#111827"


def _s(v) -> str:
    return "" if v is None else str(v)


def validate(fig) -> dict | None:
    """형식이 틀린 그림은 None(그림 없이)."""
    if not isinstance(fig, dict):
        return None
    kind = fig.get("kind")
    caption = _s(fig.get("caption")).strip() or None
    if kind == "tree":
        nodes = fig.get("nodes")
        if not isinstance(nodes, list) or not nodes or len(nodes) > MAX_TREE or nodes[0] is None:
            return None
        clean = [None if v is None or _s(v).strip() == "" else _s(v).strip() for v in nodes]
        if clean[0] is None:
            return None
        for i in range(1, len(clean)):
            if clean[i] is not None and clean[(i - 1) // 2] is None:
                return None
        while clean and clean[-1] is None:
            clean.pop()
        return {"kind": "tree", "nodes": clean, "caption": caption}
    if kind == "array":
        items = fig.get("items")
        if not isinstance(items, list) or not items or len(items) > MAX_ITEMS:
            return None
        start = fig.get("start", 0)
        start = start if start in (0, 1) else 0
        return {"kind": "array", "items": [_s(v) for v in items], "start": start, "caption": caption}
    if kind == "table":
        header = fig.get("header")
        rows = fig.get("rows")
        if not isinstance(header, list) or not header or len(header) > MAX_COLS:
            return None
        if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
            return None
        for r in rows:
            if not isinstance(r, list) or len(r) != len(header):
                return None
        return {"kind": "table", "header": [_s(h) for h in header],
                "rows": [[_s(c) for c in r] for r in rows], "caption": caption}
    return None


def tree_svg(fig: dict) -> str:
    nodes = fig["nodes"]
    n = len(nodes)
    depth = n.bit_length()  # 레벨 수
    width = max(60 * (2 ** (depth - 1)), 120)
    height = 50 + 70 * (depth - 1) + 30
    pos = {}
    for i, v in enumerate(nodes):
        if v is None:
            continue
        level = (i + 1).bit_length() - 1
        idx = i + 1 - 2 ** level
        x = (idx + 0.5) * width / (2 ** level)
        y = 30 + level * 70
        pos[i] = (x, y)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}">',
             f'<rect x="0" y="0" width="{width}" height="{height}" fill="{_FILL}"/>']
    for i in pos:
        if i == 0:
            continue
        px, py = pos[(i - 1) // 2]
        x, y = pos[i]
        parts.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{_STROKE}" stroke-width="2"/>')
    for i, (x, y) in pos.items():
        label = html.escape(nodes[i])
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="18" fill="{_FILL}" stroke="{_STROKE}" stroke-width="2"/>')
        parts.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="14" '
                     f'font-family="sans-serif" fill="{_TEXT}">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def _cap(fig: dict) -> str:
    c = fig.get("caption")
    return f'<div style="font-size:0.9em;color:#475569;margin-bottom:4px">{html.escape(c)}</div>' if c else ""


def figure_html(fig: dict | None) -> str:
    """화면·내려받기 공용 HTML. 트리는 data URI 그림(st.html이 <svg>를 지우므로)."""
    if not fig:
        return ""
    box = '<div class="bt-figure" style="margin:8px 0 12px 0;overflow-x:auto">'
    if fig["kind"] == "tree":
        b64 = base64.b64encode(tree_svg(fig).encode("utf-8")).decode("ascii")
        alt = html.escape(figure_text(fig), quote=True).replace("\n", " / ")
        return (box + _cap(fig) + f'<img alt="{alt}" style="max-width:100%;background:#fff;border-radius:8px" '
                f'src="data:image/svg+xml;base64,{b64}"/></div>')
    cell = "border:1px solid #94a3b8;padding:4px 10px;text-align:center;background:#fff;color:#111827"
    head = "border:1px solid #94a3b8;padding:4px 10px;text-align:center;background:#e2e8f0;color:#334155;font-size:0.85em"
    if fig["kind"] == "array":
        idx = "".join(f'<td style="{head}">{i + fig["start"]}</td>' for i in range(len(fig["items"])))
        val = "".join(f'<td style="{cell}">{html.escape(v)}</td>' for v in fig["items"])
        return (box + _cap(fig) + f'<table style="border-collapse:collapse"><tr>{idx}</tr><tr>{val}</tr></table></div>')
    if fig["kind"] == "table":
        h = "".join(f'<th style="{head}">{html.escape(x)}</th>' for x in fig["header"])
        rows = "".join("<tr>" + "".join(f'<td style="{cell}">{html.escape(c)}</td>' for c in r) + "</tr>"
                       for r in fig["rows"])
        return box + _cap(fig) + f'<table style="border-collapse:collapse"><tr>{h}</tr>{rows}</table></div>'
    return ""


def figure_text(fig: dict | None) -> str:
    """채점(03-B)·보완 설명(04)에 넣는 글 표현."""
    if not fig:
        return ""
    cap = f" ({fig['caption']})" if fig.get("caption") else ""
    if fig["kind"] == "tree":
        nodes = fig["nodes"]
        lines = [f"이진 트리{cap}, 레벨 순서(빈자리 null): [" + ", ".join("null" if v is None else v for v in nodes) + "]"]
        for i, v in enumerate(nodes):
            if v is None:
                continue
            kids = []
            for side, j in (("왼쪽", 2 * i + 1), ("오른쪽", 2 * i + 2)):
                if j < len(nodes) and nodes[j] is not None:
                    kids.append(f"{side} 자식 {nodes[j]}")
            if kids:
                lines.append(f"- {v}: " + ", ".join(kids))
        return "\n".join(lines)
    if fig["kind"] == "array":
        return f"배열{cap}, 인덱스 {fig['start']}부터: " + ", ".join(
            f"[{i + fig['start']}]={v}" for i, v in enumerate(fig["items"]))
    if fig["kind"] == "table":
        rows = "\n".join(" | ".join(r) for r in fig["rows"])
        return f"표{cap}\n" + " | ".join(fig["header"]) + "\n" + rows
    return ""


_PAGE_REF = re.compile(r"(p\.\s*\d+|\d+\s*쪽|\d+\s*페이지|슬라이드)", re.I)
_FIG_REF = re.compile(r"(그림|(위|아래|오른쪽|왼쪽|다음)(의)?\s*(트리|배열|표|도식))")


def refers_to_page_or_figure(text: str, has_figure: bool) -> bool:
    """문제 글이 페이지를 가리키거나, 그림 없이 그림·트리·표를 가리키면 True."""
    text = text or ""
    if _PAGE_REF.search(text):
        return True
    if not has_figure and _FIG_REF.search(text):
        return True
    return False
