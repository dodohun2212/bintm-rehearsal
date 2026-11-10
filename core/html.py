"""화면(screens)과 내려받기(export)가 함께 쓰는 HTML 도우미. 같은 도우미를 두 곳에 만들지 않는다."""
from __future__ import annotations

import html as _html
import re

DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다."
PCT_NOTE = ("출제 가능성 점수는 자료와 녹음의 신호를 정해진 규칙(가중치 v0)으로 더해, 가장 높은 개념을 100점으로 "
            "맞춘 비교용 점수예요. 확률이 아니며 실제 출제를 보장하지 않습니다.")
FOOTER = "이 결과는 자료와 녹음의 신호를 규칙대로 더한 것으로, 실제 출제를 보장하지 않습니다."
NO_EXPLAIN_NOTE = "보완 설명은 앱 ④에서 '설명 보기'로 만들 수 있어요."
NOT_FOUND_LABEL = "올린 자료에서 찾지 못함"

STATUS_KIND = {"앎": "ok", "헷갈림": "mid", "모름": "bad", "진단 안 함": "none"}
ACTION_KIND = {"지금 당장": "bad", "다음": "mid", "복습만": "none"}
CIRCLED = "①②③④"
_HAS_BATCHIM = {0: True, 1: False, 2: True, 3: False}  # 일, 이, 삼, 사

# 밝은·어두운 화면 모두에서 보이는 고정 색
CSS = """
.bt-card{border:1px solid #d0d7e2;border-radius:12px;padding:14px 16px;margin:10px 0;background:rgba(127,127,127,.04)}
.bt-bd{display:inline-block;padding:1px 9px;margin:2px 4px 2px 0;border-radius:999px;font-size:.82em;font-weight:600;
  border:1px solid #9aa4b2;color:#334155;background:#eef2f7;line-height:1.6;white-space:nowrap}
.bt-bd-ok{background:#dcfce7;border-color:#16a34a;color:#14532d}
.bt-bd-mid{background:#fef9c3;border-color:#ca8a04;color:#713f12}
.bt-bd-bad{background:#fee2e2;border-color:#dc2626;color:#7f1d1d}
.bt-bd-none{background:#e5e7eb;border-color:#6b7280;color:#374151}
.bt-bd-blue{background:#dbeafe;border-color:#2563eb;color:#1e3a8a}
.bt-bd-neg{background:#f1f5f9;border-color:#94a3b8;color:#64748b;text-decoration:line-through}
.bt-pg{display:inline-block;padding:0 6px;margin:0 2px;border-radius:6px;font-size:.78em;font-weight:700;
  background:#dbeafe;color:#1e3a8a;border:1px solid #93c5fd;white-space:nowrap}
.bt-rec{display:inline-block;padding:0 6px;margin:0 2px;border-radius:6px;font-size:.78em;font-weight:700;
  background:#ede9fe;color:#4c1d95;border:1px solid #c4b5fd;white-space:nowrap}
.bt-gap{border-left:4px solid #dc2626;padding:8px 12px;margin:8px 0;background:rgba(220,38,38,.07);border-radius:6px}
.bt-conf{border-left:4px solid #2563eb;padding:8px 12px;margin:8px 0;background:rgba(37,99,235,.07);border-radius:6px}
.bt-nf{border:1px solid #ca8a04;padding:8px 12px;margin:8px 0;background:#fef9c3;color:#713f12;border-radius:6px}
.bt-warn{border:1px solid #ca8a04;padding:8px 12px;margin:8px 0;background:#fef9c3;color:#713f12;border-radius:8px}
.bt-red{color:#dc2626;font-weight:600}
.bt-muted{color:#6b7280;font-size:.9em}
.bt-q{font-size:1.08em;font-weight:600;margin:6px 0}
.bt-bar{height:9px;border-radius:5px;background:#e5e7eb;overflow:hidden;min-width:60px}
.bt-bar>span{display:block;height:100%;background:#2563eb}
.bt-choices{list-style:none;padding-left:0;margin:6px 0}
.bt-choices li{padding:4px 8px;margin:3px 0;border-radius:6px;border:1px solid #d0d7e2}
.bt-choices li.right{border-color:#16a34a;background:#dcfce7;color:#14532d}
.bt-choices li.wrong{border-color:#dc2626;background:#fee2e2;color:#7f1d1d}
.bt-fig{margin:8px 0}
.bt-fig .cap{font-size:.85em;color:#6b7280;margin-bottom:4px}
.bt-fig table{border-collapse:collapse;margin:4px 0}
.bt-fig td,.bt-fig th{border:1px solid #94a3b8;padding:4px 10px;text-align:center;background:#fff;color:#111}
.bt-fig .idx td{background:#f1f5f9;color:#475569;font-size:.8em;border-top:none}
.bt-fig img{max-width:100%;background:#fff;border-radius:8px;border:1px solid #d0d7e2}
.bt-tbl{border-collapse:collapse;width:100%;font-size:.92em}
.bt-tbl th,.bt-tbl td{border-bottom:1px solid #d0d7e2;padding:6px 6px;text-align:left;vertical-align:middle}
.bt-p{margin:.4em 0 .8em 0;line-height:1.75}
"""


def esc(s) -> str:
    """HTML 이스케이프 (작은따옴표는 그대로 두어 &#x27;로 보이지 않게)."""
    return _html.escape("" if s is None else str(s), quote=False)


def esc_attr(s) -> str:
    return _html.escape("" if s is None else str(s), quote=True)


_CITE_ESC = re.compile(r"\s?\(\s*p\.\s*(\d+(?:\s*[,·~\-–]\s*(?:p\.\s*)?\d+)*)\s*\)")


def cite_badges(escaped: str) -> str:
    """이스케이프된 글의 (p.n)·(녹음)을 배지로."""
    def pg(m):
        nums = re.findall(r"\d+", m.group(1))
        return " " + "".join(f'<span class="bt-pg">p.{n}</span>' for n in nums)

    out = _CITE_ESC.sub(pg, escaped)
    return re.sub(r"\s?\(녹음\)", ' <span class="bt-rec">녹음</span>', out)


def rich(text) -> str:
    """한 줄 글: 이스케이프 + 인용 배지."""
    return cite_badges(esc(text))


def paragraphs(text) -> str:
    """빈 줄로 나눈 문단마다 <p>."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "".join(f'<p class="bt-p">{cite_badges(esc(p)).replace(chr(10), "<br>")}</p>' for p in parts)


def badge(text, kind: str = "") -> str:
    cls = f"bt-bd bt-bd-{kind}" if kind else "bt-bd"
    return f'<span class="{cls}">{esc(text)}</span>'


def status_badge(status: str) -> str:
    return badge(status, STATUS_KIND.get(status, "none"))


def action_badge(action: str) -> str:
    return badge(action, ACTION_KIND.get(action, "none"))


def page_badges(pages) -> str:
    return "".join(f'<span class="bt-pg">p.{int(p)}</span>' for p in pages or [])


def bar(pct, color: str = "#2563eb") -> str:
    pct = max(0, min(100, int(pct or 0)))
    return f'<div class="bt-bar"><span style="width:{pct}%;background:{color}"></span></div>'


def choice_label(i: int) -> str:
    return CIRCLED[i] if 0 <= i < len(CIRCLED) else "?"


def choice_obj(i: int) -> str:
    """①을·②를·③을·④를"""
    return choice_label(i) + ("을" if _HAS_BATCHIM.get(i, True) else "를")


def choice_is(i: int) -> str:
    """①이에요·②예요·③이에요·④예요"""
    return choice_label(i) + ("이에요" if _HAS_BATCHIM.get(i, True) else "예요")


def signal_badges(reasons: list[dict]) -> str:
    """출제 근거 배지. 감점 신호는 줄 그은 회색. 같은 유형 발화는 묶어서 ×n."""
    out = []
    counts: dict[str, int] = {}
    for r in reasons:
        k = r["kind"]
        if k in ("objective", "page", "example", "exercise"):
            out.append(badge(r["label"], "blue" if k == "objective" else ""))
        else:
            counts[k] = counts.get(k, 0) + 1
    names = {"emphasis": "강조", "exam_hint": "시험 암시", "mistake_warning": "실수 경고",
             "exercise_hint": "연습문제 지목", "question": "학우 질문", "deferral": "다음에 다룸",
             "skip": "가볍게 넘어감"}
    for k, n in counts.items():
        label = names.get(k, k) + (f" ×{n}" if n > 1 else "")
        out.append(badge(label, "neg" if k in ("deferral", "skip") else "mid"))
    return "".join(out)


def question_review_html(q: dict, g: dict | None, ans: dict, figure_html: str = "") -> str:
    """'내 문제와 답 다시 보기' 안의 내용 (화면·내려받기 공용)."""
    if not q:
        return '<p class="bt-muted">문제가 없어요.</p>'
    parts = [f'<div class="bt-q">{esc(q.get("question", ""))}</div>', figure_html]
    if q.get("kind") == "객관식":
        choice = ans.get("mcq_choice")
        items = []
        for i, c in enumerate(q.get("choices") or []):
            cls = "right" if i == q.get("answer_index") else ("wrong" if i == choice else "")
            tag = ""
            if i == q.get("answer_index"):
                tag += " ✔ 정답"
            if i == choice:
                tag += " · 내 답"
            items.append(f'<li class="{cls}">{choice_label(i)} {esc(c)}<b>{esc(tag)}</b></li>')
        parts.append(f'<ul class="bt-choices">{"".join(items)}</ul>')
        if choice == -1:
            parts.append('<p>내 답: <b>모르겠어요</b></p>')
        if ans.get("guessed") and choice is not None and choice >= 0:
            parts.append('<p class="bt-muted">확신 없이 골랐어요 (찍었어요)</p>')
        if ans.get("confusion"):
            parts.append(f'<div class="bt-conf">💬 내가 헷갈린 점: {esc(ans["confusion"])}</div>')
    else:
        if ans.get("dont_know"):
            parts.append('<p>내 답: <b>모르겠어요</b></p>')
        else:
            parts.append(f'<p><b>내 답</b></p><div class="bt-card">{esc(ans.get("answer", "")) or "(빈 답)"}</div>')
    if g:
        line = f'{status_badge(g.get("status", ""))} <b>{int(g.get("score", 0))}/10</b>'
        if g.get("error_type"):
            line += " " + badge(g["error_type"])
        parts.append(f"<p>{line}</p>")
        if g.get("reason"):
            parts.append(f'<p>채점 이유: {rich(g["reason"])}</p>')
    if q.get("kind") == "객관식":
        if q.get("explanation"):
            parts.append(f'<p><b>해설</b> {rich(q["explanation"])}</p>')
    else:
        parts.append(f'<p><b>모범 답안</b> {esc(q.get("answer", ""))}</p>')
        rub = q.get("rubric") or []
        rs = (g or {}).get("rubric_scores")
        if rub:
            rows = []
            for i, r in enumerate(rub):
                got = f"{rs[i]}/" if isinstance(rs, list) and i < len(rs) else ""
                rows.append(f"<li>{esc(r.get('point', ''))} — {got}{int(r.get('score', 0))}점</li>")
            parts.append(f"<p><b>채점 기준</b></p><ul>{''.join(rows)}</ul>")
    if q.get("source_pages"):
        parts.append(f'<p class="bt-muted">근거 페이지 {page_badges(q["source_pages"])}</p>')
    return "".join(p for p in parts if p)


def explanation_html(ex: dict | None) -> str:
    """보완 설명 (화면·내려받기 공용): 내가 놓친 점, 헷갈린 점 답, 문단, 찾지 못함, 다시 볼 페이지."""
    if not ex:
        return f'<p class="bt-muted">{esc(NO_EXPLAIN_NOTE)}</p>'
    parts = []
    if ex.get("my_gap"):
        parts.append(f'<div class="bt-gap"><b>내가 놓친 점</b> {rich(ex["my_gap"])}</div>')
    if ex.get("confusion"):
        reply = ex.get("confusion_reply")
        body = f'<div><b>💬 내가 헷갈린 점</b> “{esc(ex["confusion"])}”</div>'
        if reply:
            body += f'<div style="margin-top:6px"><b>답</b> {rich(reply)}</div>'
        parts.append(f'<div class="bt-conf">{body}</div>')
    parts.append(paragraphs(ex.get("explanation", "")))
    if ex.get("not_found"):
        note = ex.get("not_found_note") or "올린 자료에 필요한 설명이 없어요."
        parts.append(f'<div class="bt-nf"><b>{esc(NOT_FOUND_LABEL)}</b> · {esc(note)} '
                     f'교재 다른 장이나 수업 노트를 확인하세요.</div>')
    if ex.get("check_pages"):
        parts.append(f'<p class="bt-muted">다시 볼 페이지 {page_badges(ex["check_pages"])}</p>')
    return "".join(parts)


def note_html(note: dict | None, quotes: list[dict]) -> str:
    """요약 노트 한 절 (화면·내려받기 공용)."""
    if not note:
        return '<p class="bt-muted">요약 노트를 아직 만들지 않았어요.</p>'
    parts = [paragraphs(note.get("summary", ""))]
    if note.get("key_points"):
        parts.append("<p><b>핵심</b></p><ul>" + "".join(f"<li>{rich(k)}</li>" for k in note["key_points"]) + "</ul>")
    if note.get("pitfalls"):
        parts.append("<p><b>자주 하는 실수</b></p><ul>" + "".join(f"<li>{rich(k)}</li>" for k in note["pitfalls"])
                     + "</ul>")
    if quotes:
        parts.append("<p><b>교수님 말</b></p><ul>" + "".join(
            f'<li>“{esc(u["quote"])}” <span class="bt-rec">녹음</span></li>' for u in quotes) + "</ul>")
    if note.get("source_pages"):
        parts.append(f'<p class="bt-muted">근거 페이지 {page_badges(note["source_pages"])}</p>')
    return "".join(parts)
