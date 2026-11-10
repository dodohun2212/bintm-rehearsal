# F08 문제 그림(트리·배열·표) 검사와 그리기, 페이지·그림을 가리키는 문제 찾기
import base64
import html
import re

MAX_TREE = 31
MAX_ARRAY = 20
MAX_COLS, MAX_ROWS = 6, 10


def _s(v) -> str:
    return str(v).strip()


def validate_figure(fig):
    """올바르면 다듬은 그림 dict, 아니면 None(그림 없이)."""
    if not isinstance(fig, dict):
        return None
    kind = fig.get("kind")
    caption = _s(fig.get("caption")) if fig.get("caption") else ""
    if kind == "tree":
        nodes = fig.get("nodes")
        if not isinstance(nodes, list) or not nodes or len(nodes) > MAX_TREE:
            return None
        nodes = [None if (n is None or _s(n) in ("", "null", "None")) else _s(n) for n in nodes]
        while nodes and nodes[-1] is None:
            nodes.pop()
        if not nodes or nodes[0] is None:
            return None
        for i in range(1, len(nodes)):
            if nodes[i] is not None and nodes[(i - 1) // 2] is None:
                return None
        return {"kind": "tree", "nodes": nodes, "caption": caption}
    if kind == "array":
        items = fig.get("items")
        if not isinstance(items, list) or not items or len(items) > MAX_ARRAY:
            return None
        start = fig.get("start", 0)
        try:
            start = int(start)
        except (TypeError, ValueError):
            return None
        if start not in (0, 1):
            return None
        return {"kind": "array", "items": ["" if x is None else _s(x) for x in items], "start": start,
                "caption": caption}
    if kind == "table":
        header, rows = fig.get("header"), fig.get("rows")
        if not isinstance(header, list) or not (1 <= len(header) <= MAX_COLS):
            return None
        if not isinstance(rows, list) or not (1 <= len(rows) <= MAX_ROWS):
            return None
        if any(not isinstance(r, list) or len(r) != len(header) for r in rows):
            return None
        return {"kind": "table", "header": [_s(h) for h in header],
                "rows": [[_s(c) for c in r] for r in rows], "caption": caption}
    return None


def tree_svg(fig: dict) -> str:
    """밝은·어두운 화면 모두에서 보이도록 흰 바탕과 고정 색을 쓴다."""
    nodes = fig["nodes"]
    depth = max(i.bit_length() for i in range(1, len(nodes) + 1))
    width, level_h, r = max(320, 2 ** (depth - 1) * 56), 70, 20
    height = depth * level_h + 10
    pos = {}
    for i, v in enumerate(nodes):
        if v is None:
            continue
        level = (i + 1).bit_length() - 1
        idx = i + 1 - 2 ** level
        x = (idx + 0.5) * width / (2 ** level)
        y = level * level_h + 35
        pos[i] = (x, y)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}">',
             f'<rect width="{width}" height="{height}" fill="#ffffff"/>']
    for i, (x, y) in pos.items():
        if i > 0:
            px, py = pos[(i - 1) // 2]
            parts.append(f'<line x1="{px:.1f}" y1="{py:.1f}" x2="{x:.1f}" y2="{y:.1f}" '
                         f'stroke="#475569" stroke-width="2"/>')
    for i, (x, y) in pos.items():
        label = html.escape(nodes[i])
        size = 16 if len(nodes[i]) <= 3 else 11
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="#e8f0fe" stroke="#2563eb" stroke-width="2"/>')
        parts.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="{size}" '
                     f'font-family="sans-serif" fill="#111827">{label}</text>')
    parts.append("</svg>")
    return "".join(parts)


def figure_html(fig) -> str:
    """화면·내보내기용 HTML. 트리는 data URI 그림(st.html이 <svg>를 지우기 때문)."""
    fig = validate_figure(fig) if fig and "kind" in fig else None
    if not fig:
        return ""
    cap = f'<div class="fig-cap">{html.escape(fig["caption"])}</div>' if fig.get("caption") else ""
    box = ('<div class="bt-fig" style="margin:8px 0 12px;overflow-x:auto;">{cap}{body}</div>')
    if fig["kind"] == "tree":
        b64 = base64.b64encode(tree_svg(fig).encode("utf-8")).decode("ascii")
        alt = html.escape(figure_text(fig) or "이진 트리", quote=True)
        body = (f'<img alt="{alt}" src="data:image/svg+xml;base64,{b64}" '
                f'style="max-width:100%;height:auto;border:1px solid #cbd5e1;border-radius:8px;"/>')
        return box.format(cap=cap, body=body)
    td = 'style="border:1px solid #94a3b8;padding:6px 12px;text-align:center;background:#ffffff;color:#111827;"'
    th = 'style="border:1px solid #94a3b8;padding:6px 12px;text-align:center;background:#e2e8f0;color:#111827;"'
    if fig["kind"] == "array":
        idx = "".join(f"<td {th}>{i + fig['start']}</td>" for i in range(len(fig["items"])))
        val = "".join(f"<td {td}>{html.escape(v)}</td>" for v in fig["items"])
        body = f'<table style="border-collapse:collapse;"><tr>{idx}</tr><tr>{val}</tr></table>'
        return box.format(cap=cap, body=body)
    head = "".join(f"<th {th}>{html.escape(h)}</th>" for h in fig["header"])
    rows = "".join("<tr>" + "".join(f"<td {td}>{html.escape(c)}</td>" for c in r) + "</tr>" for r in fig["rows"])
    body = f'<table style="border-collapse:collapse;"><tr>{head}</tr>{rows}</table>'
    return box.format(cap=cap, body=body)


def figure_text(fig) -> str | None:
    """채점(03-B)과 보완 설명(04)에 넣을 글. 그림이 없으면 None."""
    fig = validate_figure(fig) if fig else None
    if not fig:
        return None
    cap = f"{fig['caption']} " if fig.get("caption") else ""
    if fig["kind"] == "tree":
        nodes = fig["nodes"]
        rel = []
        for i, v in enumerate(nodes):
            if v is None:
                continue
            kids = []
            for side, j in (("왼쪽", 2 * i + 1), ("오른쪽", 2 * i + 2)):
                if j < len(nodes) and nodes[j] is not None:
                    kids.append(f"{side} 자식 {nodes[j]}")
            if kids:
                rel.append(f"{v}의 " + ", ".join(kids))
        shown = ", ".join("null" if v is None else v for v in nodes)
        return f"{cap}이진 트리(레벨 순서, 빈자리 null): [{shown}]. 루트 {nodes[0]}. " + "; ".join(rel)
    if fig["kind"] == "array":
        pairs = ", ".join(f"[{i + fig['start']}]={v}" for i, v in enumerate(fig["items"]))
        return f"{cap}배열(인덱스 {fig['start']}부터): {pairs}"
    rows = " / ".join(" | ".join(r) for r in fig["rows"])
    return f"{cap}표: {' | '.join(fig['header'])} / {rows}"


_PAGE_REF = re.compile(r"p\.\s*\d+|\d+\s*쪽|슬라이드\s*\d*|페이지\s*\d+|\d+\s*페이지")
_FIG_WORDS = re.compile(r"그림|(오른쪽|왼쪽|위|아래|다음|주어진)\s*(의\s*)?(트리|표|배열)")


def refers_elsewhere(question: str, figure) -> bool:
    """문제 글이 페이지를 가리키거나, 그림 없이 그림·트리·표를 가리키면 True."""
    q = question or ""
    if _PAGE_REF.search(q):
        return True
    if not figure and _FIG_WORDS.search(q):
        return True
    return False
