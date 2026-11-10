"""F08 문제 그림(트리·배열·표) 검사와 그리기, 페이지·그림을 가리키는 문제 찾기."""
from __future__ import annotations

import base64
import html
import math
import re

MAX_TREE = 31
MAX_ARRAY = 32
MAX_COLS = 6
MAX_ROWS = 10

# 밝은·어두운 화면 모두에서 보이는 고정 색
NODE_FILL = "#eef4ff"
NODE_STROKE = "#2f5bd3"
EDGE = "#5b6b8c"
TEXT = "#14213d"


def _cell(v) -> str:
    return "" if v is None else str(v).strip()


def check_figure(fig) -> dict | None:
    """형식이 맞으면 다듬은 figure, 틀리면 None(그림 없이)."""
    if not isinstance(fig, dict):
        return None
    kind = fig.get("kind")
    caption = fig.get("caption") if isinstance(fig.get("caption"), str) else None
    if kind == "tree":
        nodes = fig.get("nodes")
        if not isinstance(nodes, list) or not nodes or len(nodes) > MAX_TREE:
            return None
        nodes = [None if (v is None or _cell(v) in ("", "null", "None")) else _cell(v) for v in nodes]
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
        start = fig.get("start", 0)
        if not isinstance(items, list) or not items or len(items) > MAX_ARRAY:
            return None
        if start not in (0, 1):
            return None
        return {"kind": "array", "items": [_cell(v) for v in items], "start": start, "caption": caption}
    if kind == "table":
        header, rows = fig.get("header"), fig.get("rows")
        if not isinstance(header, list) or not (1 <= len(header) <= MAX_COLS):
            return None
        if not isinstance(rows, list) or not (1 <= len(rows) <= MAX_ROWS):
            return None
        if any(not isinstance(r, list) or len(r) != len(header) for r in rows):
            return None
        return {"kind": "table", "header": [_cell(h) for h in header],
                "rows": [[_cell(c) for c in r] for r in rows], "caption": caption}
    return None


def tree_svg(fig: dict) -> str:
    """레벨 순서 노드 목록 → SVG (원과 선)."""
    nodes = fig["nodes"]
    depth = int(math.floor(math.log2(len(nodes)))) + 1
    width = max(240, 2 ** (depth - 1) * 56)
    level_h, r = 64, 18
    height = depth * level_h + 10
    pos = {}
    for i, v in enumerate(nodes):
        if v is None:
            continue
        level = int(math.floor(math.log2(i + 1)))
        idx = i + 1 - 2 ** level
        slots = 2 ** level
        pos[i] = ((idx + 0.5) * width / slots, level * level_h + r + 8)
    lines, circles = [], []
    for i, (x, y) in pos.items():
        if i > 0:
            px, py = pos[(i - 1) // 2]
            lines.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                         f'stroke="{EDGE}" stroke-width="2"/>')
    for i, (x, y) in pos.items():
        label = html.escape(str(nodes[i]))
        size = 15 if len(label) <= 3 else 11
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{NODE_FILL}" '
                       f'stroke="{NODE_STROKE}" stroke-width="2"/>'
                       f'<text x="{x:.1f}" y="{y + 5:.1f}" font-size="{size}" text-anchor="middle" '
                       f'font-family="sans-serif" fill="{TEXT}">{label}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height}" '
            f'viewBox="0 0 {width:.0f} {height}">' + "".join(lines) + "".join(circles) + "</svg>")


def tree_img(fig: dict) -> str:
    """st.html이 <svg>를 지우므로 data URI <img>로 넣는다."""
    b64 = base64.b64encode(tree_svg(fig).encode("utf-8")).decode("ascii")
    alt = html.escape(figure_text(fig) or "이진 트리", quote=True)
    return (f'<img alt="{alt}" style="max-width:100%;height:auto" '
            f'src="data:image/svg+xml;base64,{b64}"/>')


def figure_html(fig: dict | None) -> str:
    """문제 아래에 붙일 그림 HTML. 글은 모두 이스케이프."""
    if not fig:
        return ""
    cap = f'<div class="fig-cap">{html.escape(fig["caption"])}</div>' if fig.get("caption") else ""
    if fig["kind"] == "tree":
        body = tree_img(fig)
    elif fig["kind"] == "array":
        start = fig.get("start", 0)
        idx = "".join(f"<th>{start + i}</th>" for i in range(len(fig["items"])))
        vals = "".join(f"<td>{html.escape(v)}</td>" for v in fig["items"])
        body = (f'<table class="fig-array"><tr class="idx"><th>인덱스</th>{idx}</tr>'
                f'<tr><th>값</th>{vals}</tr></table>')
    else:
        head = "".join(f"<th>{html.escape(h)}</th>" for h in fig["header"])
        rows = "".join("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in r) + "</tr>"
                       for r in fig["rows"])
        body = f'<table class="fig-table"><tr>{head}</tr>{rows}</table>'
    return f'<div class="figure">{cap}{body}</div>'


def figure_text(fig: dict | None) -> str | None:
    """채점(03-B)·보완 설명(04)에 넣는 그림의 글 표현."""
    if not fig:
        return None
    cap = f"{fig['caption']}: " if fig.get("caption") else ""
    if fig["kind"] == "tree":
        nodes = fig["nodes"]
        edges = []
        for i, v in enumerate(nodes):
            if v is None:
                continue
            for j, side in ((2 * i + 1, "왼쪽"), (2 * i + 2, "오른쪽")):
                if j < len(nodes) and nodes[j] is not None:
                    edges.append(f"{v}의 {side} 자식 {nodes[j]}")
        listing = ", ".join("null" if v is None else v for v in nodes)
        return f"{cap}이진 트리(레벨 순서, 빈자리 null): [{listing}] / " + "; ".join(edges or ["자식 없음"])
    if fig["kind"] == "array":
        start = fig.get("start", 0)
        return cap + f"배열(인덱스 {start}부터): " + ", ".join(
            f"[{start + i}]={v}" for i, v in enumerate(fig["items"]))
    rows = " / ".join(" | ".join(r) for r in fig["rows"])
    return cap + "표: " + " | ".join(fig["header"]) + " / " + rows


_PAGE_REF = re.compile(r"(p\.\s*\d+|\d+\s*쪽|\d+\s*페이지|슬라이드)", re.IGNORECASE)
_FIG_WORDS = ("그림", "위 트리", "아래 트리", "오른쪽 트리", "왼쪽 트리", "다음 트리",
              "위 표", "아래 표", "다음 표", "위 배열", "아래 배열", "다음 배열")


def points_away(question: str, has_figure: bool) -> bool:
    """문제 글이 학생이 볼 수 없는 페이지·그림을 가리키면 True."""
    text = question or ""
    if _PAGE_REF.search(text):
        return True
    if not has_figure and any(w in text for w in _FIG_WORDS):
        return True
    return False
