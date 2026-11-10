"""F10 결과 HTML 파일 2개: study_html(공부 순서·오답노트), notes_html(요약 노트).

외부 호출이 없는 순수 함수. 모든 글은 이스케이프하고, 원본 페이지 그림은 넣지 않는다.
"""
from __future__ import annotations

import html
import re

from core.figure import figure_html
from core.priority import group_by_action

DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다"
FOOTER = "이 결과는 자료와 녹음의 신호를 규칙대로 더한 것으로, 실제 출제를 보장하지 않습니다."
NO_EXPLAIN = "보완 설명은 앱 ④에서 '설명 보기'로 만들 수 있어요."
ACTION_NOTE = {
    "지금 당장": "출제 점수가 높은데 아직 모르는 개념이에요. 여기부터 보세요.",
    "다음": "출제 점수가 중간이거나 헷갈린 개념이에요.",
    "복습만": "이미 알거나 출제 점수가 낮은 개념이에요. '진단 안 함'은 출제 가능성 점수가 20점 미만이라 문제를 내지 않은 개념이에요.",
}
STATUS_CLASS = {"앎": "ok", "헷갈림": "mid", "모름": "bad", "진단 안 함": "none"}
_CITE = re.compile(r"\((p\.\s?\d+(?:\s*[,~\-]\s*(?:p\.)?\s?\d+)*)\)")

CSS = """
:root{--bg:#ffffff;--fg:#1f2937;--muted:#6b7280;--line:#e5e7eb;--card:#f9fafb;--blue:#2563eb;
--ok:#15803d;--okbg:#dcfce7;--mid:#a16207;--midbg:#fef9c3;--bad:#b91c1c;--badbg:#fee2e2;--warnbg:#fffbeb}
@media (prefers-color-scheme: dark){:root{--bg:#111827;--fg:#e5e7eb;--muted:#9ca3af;--line:#374151;--card:#1f2937;
--okbg:#14532d;--ok:#bbf7d0;--midbg:#713f12;--mid:#fef08a;--badbg:#7f1d1d;--bad:#fecaca;--warnbg:#3b2f0b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font-family:-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;font-size:16px;line-height:1.75}
main{max-width:860px;margin:0 auto;padding:28px 16px 60px}h1{font-size:26px;margin:0 0 4px}
h2{font-size:21px;margin:34px 0 10px;border-bottom:2px solid var(--blue);padding-bottom:4px}
h3{font-size:18px;margin:20px 0 6px}.info{color:var(--muted);font-size:14px}
.warn{background:var(--warnbg);border:1px solid #f59e0b;border-radius:10px;padding:10px 14px;margin:14px 0}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.stat{flex:1;min-width:110px;border:1px solid var(--line);
border-radius:10px;padding:8px 12px;background:var(--card)}.stat b{display:block;font-size:24px}
.card{border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0;background:var(--card)}
.badge{display:inline-block;border-radius:999px;padding:0 9px;font-size:13px;margin:2px 4px 2px 0;border:1px solid var(--line)}
.ok{background:var(--okbg);color:var(--ok)}.mid{background:var(--midbg);color:var(--mid)}
.bad{background:var(--badbg);color:var(--bad)}.none{color:var(--muted)}.minus{text-decoration:line-through;color:var(--muted)}
.pg{display:inline-block;background:#dbeafe;color:#1e40af;border-radius:6px;padding:0 6px;font-size:12px;margin:0 2px}
.rec{display:inline-block;background:#ede9fe;color:#5b21b6;border-radius:6px;padding:0 6px;font-size:12px;margin:0 2px}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;width:140px;display:inline-block;vertical-align:middle}
.bar i{display:block;height:100%;background:var(--blue)}.row{padding:6px 0;border-bottom:1px dashed var(--line)}
.q{font-size:17px;font-weight:600}.choice{padding:2px 6px;border-radius:6px}.right{background:var(--okbg);color:var(--ok)}
.wrong{background:var(--badbg);color:var(--bad)}.gap{border-left:4px solid #dc2626;padding:4px 10px;margin:8px 0}
.reply{border-left:4px solid var(--blue);padding:4px 10px;margin:8px 0}
.nf{background:var(--warnbg);border:1px solid #f59e0b;border-radius:8px;padding:6px 10px;margin:8px 0}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}.fig-cap{font-size:13px;color:var(--muted)}
.formula{font-size:14px;color:var(--muted)}.foot{margin-top:30px;color:var(--muted);font-size:14px}
@media print{details{display:block}details>*{display:block}.card{break-inside:avoid}}
"""


def esc(text) -> str:
    """본문 글 이스케이프(태그만 막고 따옴표는 그대로 둔다. 속성 값에는 쓰지 않는다)."""
    return html.escape("" if text is None else str(text), quote=False)


def rich(text) -> str:
    """이스케이프한 뒤 (p.n)을 페이지 배지로, (녹음)을 녹음 배지로 바꾼다."""
    out = esc(text)
    out = _CITE.sub(lambda m: f'<span class="pg">{m.group(1)}</span>', out)
    return out.replace("(녹음)", '<span class="rec">녹음</span>')


def paragraphs(text) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "".join(f"<p>{rich(p)}</p>" for p in parts)


def page_badges(pages) -> str:
    return "".join(f'<span class="pg">p.{int(p)}</span>' for p in pages or [])


def status_badge(status: str) -> str:
    return f'<span class="badge {STATUS_CLASS.get(status, "none")}">{esc(status)}</span>'


def _page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body><main>{body}</main></body></html>")


def _info_line(data: dict) -> str:
    src = {"audio": "녹음 포함", "paste": "대본 포함"}.get(data.get("transcript_source"), "녹음·대본 없음")
    return f'<div class="info">{esc(data.get("material_name") or "자료")} · {esc(data.get("today", ""))} · {src}</div>'


def _stats(items: list[tuple[str, int]]) -> str:
    return '<div class="stats">' + "".join(f'<div class="stat">{esc(k)} <b>{v}</b></div>' for k, v in items) + "</div>"


def evidence_badges(score_row: dict | None) -> str:
    if not score_row:
        return ""
    from core.score import badges

    return "".join(f'<span class="badge{" minus" if minus else ""}">{esc(label)}</span>' for label, minus in badges(score_row))


def question_block(q: dict, g: dict | None, answer: str = "", choice=None, guessed=False, confusion="") -> str:
    """문제와 그림, 객관식 보기(정답·내 답 표시) 또는 서술형 내 답, 채점, 해설·모범 답안."""
    out = [f'<div class="q">{esc(q["question"])}</div>', figure_html(q.get("figure"))]
    if q["kind"] == "객관식":
        items = []
        for i, c in enumerate(q["choices"]):
            cls = "right" if i == q["answer_index"] else ("wrong" if i == choice else "")
            mark = " ← 정답" if i == q["answer_index"] else (" ← 내 답" if i == choice else "")
            items.append(f'<li class="choice {cls}">{"①②③④"[i]} {esc(c)}{mark}</li>')
        if choice == -1:
            items.append('<li class="choice wrong">모르겠어요 ← 내 답</li>')
        out.append("<ul>" + "".join(items) + "</ul>")
        if guessed and choice is not None and choice >= 0:
            out.append("<div>확신 없이 골랐어요 (찍었어요)</div>")
        if confusion:
            out.append(f"<div>💬 내가 헷갈린 점: {esc(confusion)}</div>")
    else:
        out.append(f"<div><b>내 답</b>: {esc(answer) if (answer or '').strip() else '(모르겠어요 / 답 없음)'}</div>")
    if g:
        err = f" · {esc(g['error_type'])}" if g.get("error_type") else ""
        out.append(f'<div>{status_badge(g["status"])} <b>{g["score"]}/10</b>{err} — {rich(g.get("reason", ""))}</div>')
    if q["kind"] == "객관식":
        out.append(f"<div><b>해설</b>: {rich(q.get('explanation') or '')}</div>")
    else:
        rub = ", ".join(f"{esc(r['point'])} {r['score']}점" for r in q.get("rubric") or [])
        out.append(f"<div><b>모범 답안</b>: {esc(q['answer'])}</div><div class=\"formula\">루브릭: {rub}</div>")
    out.append(f"<div>근거 {page_badges(q.get('source_pages'))}</div>")
    return "".join(out)


def explanation_block(e: dict | None) -> str:
    if not e:
        return f'<div class="nf">{esc(NO_EXPLAIN)}</div>'
    out = [f'<div class="gap"><b>내가 놓친 점</b>: {rich(e.get("my_gap"))}</div>']
    if e.get("confusion"):
        reply = f"<div>{rich(e['confusion_reply'])}</div>" if e.get("confusion_reply") else ""
        out.append(f'<div class="reply"><b>💬 내가 헷갈린 점에 대한 답</b><div>“{esc(e["confusion"])}”</div>{reply}</div>')
    out.append(paragraphs(e.get("explanation")))
    if e.get("not_found"):
        out.append(f'<div class="nf">올린 자료에서 찾지 못함 — {esc(e.get("not_found_note"))}. 교재 다른 장이나 수업 노트를 확인하세요.</div>')
    out.append(f"<div>다시 볼 페이지 {page_badges(e.get('check_pages'))}</div>")
    return "".join(out)


def _card(p: dict, data: dict, score_row: dict | None) -> str:
    cid = p["concept_id"]
    q = (data.get("questions") or {}).get(cid)
    g = (data.get("grading") or {}).get(cid)
    e = (data.get("explanations") or {}).get(cid)
    head = (f'<h3>{p["rank"]}. {esc(p["name"])}</h3><div>{status_badge(p["status"])}'
            f'<span class="badge">출제 점수 {p["exam_pct"]}</span><span class="badge">우선순위 {p["priority"]}</span></div>')
    body = ""
    if q:
        body += question_block(q, g, (data.get("answers") or {}).get(cid, ""), (data.get("mcq_choice") or {}).get(cid),
                               (data.get("guessed") or {}).get(cid, False), (data.get("confusion") or {}).get(cid, ""))
    body += "<h4>보완 설명</h4>" + explanation_block(e)
    return f'<div class="card">{head}{body}</div>'


def study_html(data: dict) -> str:
    """① 공부 순서·오답노트."""
    prios = data.get("priorities") or []
    score_by = {s["concept_id"]: s for s in data.get("scores") or []}
    groups = group_by_action(prios)
    parts = ["<h1>빈틈노트 공부 순서·오답노트</h1>", _info_line(data), f'<div class="warn">{esc(DISCLAIMER)}</div>',
             _stats([(a, len(groups[a])) for a in groups])]
    parts.append("<h2>1. 공부 순서</h2>")
    if not prios:
        parts.append("<p>우선순위 없음</p>")
    for action, rows in groups.items():
        if not rows:
            continue
        parts.append(f"<h3>{esc(action)} · {len(rows)}개</h3><div class=\"info\">{esc(ACTION_NOTE[action])}</div>")
        for p in rows:
            parts.append(
                f'<div class="row">{p["rank"]}. <b>{esc(p["name"])}</b> {status_badge(p["status"])}'
                f'<span class="bar"><i style="width:{p["exam_pct"]}%"></i></span> 출제 가능성 점수 {p["exam_pct"]}점 · '
                f'우선순위 {p["priority"]}<div>{evidence_badges(score_by.get(p["concept_id"]))}</div></div>')
    parts.append('<p class="formula">우선순위 = 출제 점수 × (1 − 이해도). 이해도: 앎 1.0 · 헷갈림 0.5 · 모름 0 · 진단 안 함 0.5. '
                 "50 이상 지금 당장, 20~49 다음, 20 미만 복습만.</p>")
    graded = [p for p in prios if p["concept_id"] in (data.get("grading") or {})]
    wrong = [p for p in graded if p["status"] in ("모름", "헷갈림")]
    right = [p for p in graded if p["status"] == "앎"]
    parts.append("<h2>2. 오답노트</h2>")
    if not graded:
        parts.append("<p>진단하지 않음</p>")
    elif not wrong:
        parts.append("<p>틀리거나 헷갈린 문제가 없어요.</p>")
    parts.extend(_card(p, data, score_by.get(p["concept_id"])) for p in wrong)
    parts.append(f"<h2>3. 맞힌 문제 · {len(right)}개</h2>")
    if right:
        parts.append("<details><summary>눌러서 펼치기</summary>" +
                     "".join(_card(p, data, score_by.get(p["concept_id"])) for p in right) + "</details>")
    extra = [p for p in prios if p["concept_id"] not in (data.get("grading") or {})
             and p["concept_id"] in (data.get("explanations") or {})]
    if extra:
        parts.append("<h2>4. 진단하지 않은 개념 설명</h2>")
        parts.extend(_card(p, data, score_by.get(p["concept_id"])) for p in extra)
    parts.append(f'<div class="foot">{esc(FOOTER)}</div>')
    return _page("빈틈노트 공부 순서·오답노트", "".join(parts))


def notes_html(data: dict) -> str:
    """② 시험 대비 요약 노트 (강의 순서)."""
    notes = data.get("notes") or {}
    concepts = {c["id"]: c for c in data.get("concepts") or []}
    prio_by = {p["concept_id"]: p for p in data.get("priorities") or []}
    order = [cid for cid in data.get("note_order") or list(notes) if cid in notes]
    counts = [(d, sum(1 for cid in order if notes[cid].get("detail") == d)) for d in ("자세히", "보통", "짧게")]
    parts = ["<h1>빈틈노트 시험 대비 요약 노트</h1>", _info_line(data), f'<div class="warn">{esc(DISCLAIMER)}</div>',
             _stats(counts)]
    if not order:
        parts.append("<p>요약 노트 없음</p>")
    from core.note import professor_quotes

    for i, cid in enumerate(order, start=1):
        n = notes[cid]
        c = concepts.get(cid, {"name": cid})
        p = prio_by.get(cid, {})
        badges = (f'<span class="badge">{esc(n.get("detail"))}</span>'
                  + (f'<span class="badge">출제 점수 {p["exam_pct"]}</span>{status_badge(p["status"])}' if p else ""))
        body = [f'<h3>{i}. {esc(c["name"])}</h3><div>{badges}</div>', paragraphs(n.get("summary"))]
        if n.get("key_points"):
            body.append("<b>핵심</b><ul>" + "".join(f"<li>{rich(x)}</li>" for x in n["key_points"]) + "</ul>")
        if n.get("pitfalls"):
            body.append("<b>자주 하는 실수</b><ul>" + "".join(f"<li>{rich(x)}</li>" for x in n["pitfalls"]) + "</ul>")
        quotes = professor_quotes(data.get("utterances") or [], cid)
        if quotes and n.get("detail") != "짧게":
            body.append("<b>교수님 말</b><ul>" + "".join(
                f'<li>“{esc(u["quote"])}” <span class="rec">녹음</span></li>' for u in quotes) + "</ul>")
        body.append(f"<div>근거 {page_badges(n.get('source_pages'))}</div>")
        parts.append(f'<div class="card">{"".join(body)}</div>')
    parts.append(f'<div class="foot">{esc(FOOTER)}</div>')
    return _page("빈틈노트 시험 대비 요약 노트", "".join(parts))


def study_filename(day: str) -> str:
    return f"빈틈노트_공부순서_오답노트_{day}.html"


def notes_filename(day: str) -> str:
    return f"빈틈노트_요약노트_{day}.html"
