"""F08 문제 그림(트리·배열·표): 검사, 그리기, 글로 바꾸기, 그림을 가리키는 문제 찾기."""
from __future__ import annotations

import base64
import html
import math
import re

MAX_TREE = 31
MAX_COLS = 6
MAX_ROWS = 10

# 밝은·어두운 화면 모두에서 보이는 고정 색
_BG = "#ffffff"
_LINE = "#475569"
_NODE_FILL = "#eff6ff"
_NODE_STROKE = "#2563eb"
_TEXT = "#0f172a"


def _cell(v) -> str:
    return "" if v is None else str(v).strip()


def validate_figure(fig) -> dict | None:
    """형식이 맞으면 정리한 그림, 틀리면 None(그림 없이 낸다)."""
    if not isinstance(fig, dict):
        return None
    kind = fig.get("kind")
    caption = _cell(fig.get("caption"))[:80] or None
    if kind == "tree":
        nodes = fig.get("nodes")
        if not isinstance(nodes, list) or not nodes or len(nodes) > MAX_TREE:
            return None
        nodes = [None if (n is None or _cell(n) in ("", "null", "None")) else _cell(n) for n in nodes]
        while nodes and nodes[-1] is None:
            nodes.pop()
        if not nodes or nodes[0] is None:
            return None
        for i in range(1, len(nodes)):
            if nodes[i] is not None and nodes[(i - 1) // 2] is None:
                return None  # 부모 없는 노드
        return {"kind": "tree", "nodes": nodes, "caption": caption}
    if kind == "array":
        items = fig.get("items")
        if not isinstance(items, list) or not items or len(items) > MAX_TREE:
            return None
        start = fig.get("start", 0)
        start = start if start in (0, 1) else 0
        return {"kind": "array", "items": [_cell(x) for x in items], "start": start, "caption": caption}
    if kind == "table":
        header = fig.get("header")
        rows = fig.get("rows")
        if not isinstance(header, list) or not header or len(header) > MAX_COLS:
            return None
        if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
            return None
        if any(not isinstance(r, list) or len(r) != len(header) for r in rows):
            return None
        return {"kind": "table", "header": [_cell(h) for h in header],
                "rows": [[_cell(c) for c in r] for r in rows], "caption": caption}
    return None


def tree_svg(fig: dict) -> str:
    nodes = fig["nodes"]
    depth = int(math.floor(math.log2(len(nodes)))) + 1
    width = max(240, (2 ** (depth - 1)) * 56)
    level_h = 70
    height = depth * level_h + 10
    r = 18

    def pos(i: int) -> tuple[float, float]:
        d = int(math.floor(math.log2(i + 1)))
        k = i - (2 ** d - 1)
        x = (k + 0.5) / (2 ** d) * width
        y = d * level_h + 30
        return x, y

    lines, circles = [], []
    for i, val in enumerate(nodes):
        if val is None:
            continue
        x, y = pos(i)
        if i > 0:
            px, py = pos((i - 1) // 2)
            lines.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="{_LINE}" stroke-width="2"/>')
        label = html.escape(val)
        size = 15 if len(val) <= 3 else 11
        circles.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{_NODE_FILL}" stroke="{_NODE_STROKE}" stroke-width="2"/>'
            f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="{size}" '
            f'font-family="sans-serif" fill="{_TEXT}">{label}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
        f'<rect width="100%" height="100%" rx="10" fill="{_BG}"/>' + "".join(lines) + "".join(circles) + "</svg>"
    )


def tree_data_uri(fig: dict) -> str:
    svg = tree_svg(fig).encode("utf-8")
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")


_TABLE_STYLE = (
    "border-collapse:collapse;margin:6px 0;background:#ffffff;color:#0f172a;font-size:15px;"
)
_TD = "border:1px solid #94a3b8;padding:4px 10px;text-align:center;"


def figure_html(fig: dict | None) -> str:
    """문제 아래에 붙일 HTML. 트리는 data URI 그림(st.html이 <svg>를 지우기 때문)."""
    fig = validate_figure(fig) if fig else None
    if not fig:
        return ""
    cap = f'<div class="fig-cap">{html.escape(fig["caption"])}</div>' if fig.get("caption") else ""
    if fig["kind"] == "tree":
        alt = html.escape(figure_text(fig), quote=True)
        body = f'<img class="fig-tree" alt="{alt}" src="{tree_data_uri(fig)}" style="max-width:100%"/>'
    elif fig["kind"] == "array":
        idx = "".join(f'<td style="{_TD}color:#64748b;font-size:12px">{i + fig["start"]}</td>' for i in range(len(fig["items"])))
        vals = "".join(f'<td style="{_TD}font-weight:600">{html.escape(v)}</td>' for v in fig["items"])
        body = f'<table class="fig-array" style="{_TABLE_STYLE}"><tr>{idx}</tr><tr>{vals}</tr></table>'
    else:
        head = "".join(f'<th style="{_TD}background:#eff6ff">{html.escape(h)}</th>' for h in fig["header"])
        rows = "".join("<tr>" + "".join(f'<td style="{_TD}">{html.escape(c)}</td>' for c in r) + "</tr>" for r in fig["rows"])
        body = f'<table class="fig-table" style="{_TABLE_STYLE}"><tr>{head}</tr>{rows}</table>'
    return f'<div class="fig">{cap}<div style="overflow-x:auto">{body}</div></div>'


def figure_text(fig: dict | None) -> str:
    """채점(03-B)·보완 설명(04)에 넣을 글."""
    fig = validate_figure(fig) if fig else None
    if not fig:
        return ""
    cap = f"{fig['caption']}: " if fig.get("caption") else ""
    if fig["kind"] == "tree":
        parts = []
        for i, v in enumerate(fig["nodes"]):
            if v is None:
                continue
            kids = [fig["nodes"][j] for j in (2 * i + 1, 2 * i + 2) if j < len(fig["nodes"])]
            left = kids[0] if kids else None
            right = kids[1] if len(kids) > 1 else None
            if left is not None or right is not None:
                parts.append(f"{v}의 왼쪽 자식 {left or '없음'}, 오른쪽 자식 {right or '없음'}")
        level = "[" + ", ".join("null" if v is None else v for v in fig["nodes"]) + "]"
        return f"{cap}이진 트리(레벨 순서 {level}). 루트 {fig['nodes'][0]}. " + "; ".join(parts)
    if fig["kind"] == "array":
        pairs = ", ".join(f"[{i + fig['start']}]={v}" for i, v in enumerate(fig["items"]))
        return f"{cap}배열(첫 인덱스 {fig['start']}): {pairs}"
    rows = " / ".join(", ".join(r) for r in fig["rows"])
    return f"{cap}표(열: {', '.join(fig['header'])}): {rows}"


_PAGE_REF = re.compile(r"(p\.\s?\d|\d+\s?쪽|\d+\s?페이지|슬라이드\s?\d|\d+\s?번\s?슬라이드)", re.IGNORECASE)
_FIG_WORDS = re.compile(r"(그림|오른쪽\s?(트리|배열|표)|왼쪽\s?(트리|배열|표)|(위|아래|다음)(의)?\s?(트리|배열|표|힙))")


def needs_fix(question: str, figure: dict | None) -> bool:
    """문제 글이 페이지를 가리키거나, 그림 없이 그림·트리·표를 가리키면 True."""
    text = question or ""
    if _PAGE_REF.search(text):
        return True
    if figure is None and _FIG_WORDS.search(text):
        return True
    return False
