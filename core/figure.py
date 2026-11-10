"""F08 문제 그림(트리·배열·표) 검사와 그리기, 페이지·그림을 가리키는 문제 찾기."""
from __future__ import annotations

import base64
import math
import re

from core.html import esc, esc_attr

MAX_TREE = 31
MAX_COLS = 6
MAX_ROWS = 10


def _cell(v) -> str:
    return "" if v is None else str(v).strip()


def validate_figure(fig) -> dict | None:
    """형식이 맞으면 정리한 dict, 아니면 None(그림 없이)."""
    if not isinstance(fig, dict):
        return None
    kind = fig.get("kind")
    cap = fig.get("caption")
    cap = str(cap).strip()[:80] if cap else None
    if kind == "tree":
        nodes = fig.get("nodes")
        if not isinstance(nodes, list) or not nodes or len(nodes) > MAX_TREE:
            return None
        nodes = [None if (n is None or str(n).strip() in ("", "null", "None")) else _cell(n) for n in nodes]
        if nodes[0] is None:
            return None
        for i in range(1, len(nodes)):
            if nodes[i] is not None and nodes[(i - 1) // 2] is None:
                return None  # 부모 없는 노드
        while nodes and nodes[-1] is None:
            nodes.pop()
        return {"kind": "tree", "nodes": nodes, "caption": cap}
    if kind == "array":
        items = fig.get("items")
        if not isinstance(items, list) or not items or len(items) > MAX_TREE:
            return None
        start = fig.get("start", 0)
        start = 1 if str(start) == "1" else 0
        return {"kind": "array", "items": [_cell(x) for x in items], "start": start, "caption": cap}
    if kind == "table":
        header, rows = fig.get("header"), fig.get("rows")
        if not isinstance(header, list) or not header or len(header) > MAX_COLS:
            return None
        if not isinstance(rows, list) or not rows or len(rows) > MAX_ROWS:
            return None
        if any(not isinstance(r, list) or len(r) != len(header) for r in rows):
            return None
        return {"kind": "table", "header": [_cell(h) for h in header],
                "rows": [[_cell(c) for c in r] for r in rows], "caption": cap}
    return None


def tree_svg(nodes: list) -> str:
    """레벨 순서 노드 목록 → SVG 글. 고정 색(밝은·어두운 화면 모두)."""
    depth = int(math.floor(math.log2(len(nodes)))) + 1
    width = max(160, (2 ** (depth - 1)) * 56)
    height = depth * 64 + 10
    pos = {}
    for i, v in enumerate(nodes):
        if v is None:
            continue
        level = int(math.floor(math.log2(i + 1)))
        k = i + 1 - 2 ** level
        x = (k + 0.5) * width / (2 ** level)
        y = 30 + level * 64
        pos[i] = (x, y)
    lines, circles = [], []
    for i, (x, y) in pos.items():
        if i > 0:
            px, py = pos[(i - 1) // 2]
            lines.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="#475569" stroke-width="2"/>')
        label = esc(nodes[i])
        fs = 15 if len(nodes[i]) <= 3 else 11
        circles.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="19" fill="#eff6ff" stroke="#1d4ed8" stroke-width="2"/>'
                       f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="{fs}" '
                       f'font-family="sans-serif" fill="#0f172a">{label}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height}" '
            f'viewBox="0 0 {width:.0f} {height}">' + "".join(lines) + "".join(circles) + "</svg>")


def figure_html(fig: dict | None) -> str:
    """화면·내려받기 공용 그림 HTML. 트리는 data URI <img>(st.html이 <svg>를 지우기 때문)."""
    fig = validate_figure(fig) if fig else None
    if not fig:
        return ""
    cap = f'<div class="cap">{esc(fig["caption"])}</div>' if fig.get("caption") else ""
    if fig["kind"] == "tree":
        b64 = base64.b64encode(tree_svg(fig["nodes"]).encode("utf-8")).decode("ascii")
        alt = esc_attr(figure_text(fig) or "문제 트리 그림")
        body = f'<img alt="{alt}" src="data:image/svg+xml;base64,{b64}">'
    elif fig["kind"] == "array":
        vals = "".join(f"<td>{esc(v)}</td>" for v in fig["items"])
        idx = "".join(f"<td>{i + fig['start']}</td>" for i in range(len(fig["items"])))
        body = f'<table><tr>{vals}</tr><tr class="idx">{idx}</tr></table>'
    else:
        head = "".join(f"<th>{esc(h)}</th>" for h in fig["header"])
        rows = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in fig["rows"])
        body = f"<table><tr>{head}</tr>{rows}</table>"
    return f'<div class="bt-fig">{cap}{body}</div>'


def figure_text(fig: dict | None) -> str | None:
    """채점(03-B)·보완 설명(04)에 넣는 그림 설명 글."""
    fig = validate_figure(fig) if fig else None
    if not fig:
        return None
    cap = f" ({fig['caption']})" if fig.get("caption") else ""
    if fig["kind"] == "tree":
        vals = ", ".join("빈자리" if v is None else v for v in fig["nodes"])
        return f"이진 트리{cap}, 레벨 순서(배열 표현 순서) 노드: [{vals}]"
    if fig["kind"] == "array":
        pairs = ", ".join(f"[{i + fig['start']}]={v}" for i, v in enumerate(fig["items"]))
        return f"배열{cap}, 첫 인덱스 {fig['start']}: {pairs}"
    rows = " / ".join(", ".join(r) for r in fig["rows"])
    return f"표{cap}, 열: {', '.join(fig['header'])} / 행: {rows}"


_PAGE_REF = re.compile(r"(p\.\s*\d+|\d+\s*쪽|\d+\s*페이지|슬라이드)")
_FIG_REF = re.compile(r"(그림|위\s*트리|아래\s*트리|오른쪽\s*트리|왼쪽\s*트리|다음\s*트리|위\s*표|아래\s*표|다음\s*표|"
                      r"아래\s*배열|위\s*배열|다음\s*배열)")


def points_outside(question: str, figure: dict | None) -> bool:
    """문제 글이 페이지를 가리키거나, 그림 없이 그림·트리·표를 가리키면 True."""
    q = question or ""
    if _PAGE_REF.search(q):
        return True
    return figure is None and bool(_FIG_REF.search(q))
