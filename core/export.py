# F10 결과 내보내기: HTML 파일 두 개. 외부 호출 없는 순수 함수. 모든 글은 이스케이프한다. 페이지 그림은 넣지 않는다.
import html
import re

from core.diagnose import CHOICE_MARKS, MCQ
from core.figure import figure_html
from core.note import lecture_order, professor_quotes

DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다."
FOOTER = "이 결과는 자료와 녹음의 신호를 규칙대로 더한 것으로, 실제 출제를 보장하지 않습니다."
STATUS_CLASS = {"앎": "ok", "헷갈림": "mid", "모름": "bad", "진단 안 함": "none"}
ACTION_DESC = {
    "지금 당장": "여기부터 보세요. 출제 가능성이 높은데 아직 모르는 개념이에요.",
    "다음": "지금 당장 다음으로 볼 개념이에요.",
    "복습만": "잘 알거나 출제 가능성이 낮은 개념이에요. 시간이 남으면 훑어보세요.",
}

CSS = """
:root{--bg:#ffffff;--fg:#1f2937;--muted:#6b7280;--line:#e5e7eb;--card:#f9fafb;--blue:#2563eb;
--ok:#15803d;--okbg:#dcfce7;--mid:#a16207;--midbg:#fef9c3;--bad:#b91c1c;--badbg:#fee2e2;--nonebg:#f3f4f6}
@media (prefers-color-scheme: dark){:root{--bg:#111827;--fg:#e5e7eb;--muted:#9ca3af;--line:#374151;--card:#1f2937;
--okbg:#14532d;--ok:#bbf7d0;--midbg:#713f12;--mid:#fef08a;--badbg:#7f1d1d;--bad:#fecaca;--nonebg:#374151}}
body{background:var(--bg);color:var(--fg);font-family:-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",sans-serif;
font-size:17px;line-height:1.75;max-width:860px;margin:0 auto;padding:24px 16px}
h1{font-size:1.6em;margin:0 0 4px}h2{margin-top:40px;border-bottom:2px solid var(--line);padding-bottom:4px}
.info{color:var(--muted);font-size:.9em}.warn{border:1px solid var(--line);border-left:4px solid var(--blue);
padding:10px 14px;border-radius:8px;margin:16px 0;background:var(--card)}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}.stat{flex:1;min-width:120px;border:1px solid var(--line);
border-radius:10px;padding:10px 14px;background:var(--card)}.stat b{display:block;font-size:1.6em}
.card{border:1px solid var(--line);border-radius:12px;padding:14px 18px;margin:14px 0;background:var(--bg)}
.badge{display:inline-block;padding:1px 9px;border-radius:999px;font-size:.8em;margin:2px 4px 2px 0;background:var(--nonebg)}
.ok{background:var(--okbg);color:var(--ok)}.mid{background:var(--midbg);color:var(--mid)}
.bad{background:var(--badbg);color:var(--bad)}.none{background:var(--nonebg)}
.pg{display:inline-block;padding:0 6px;border-radius:6px;font-size:.8em;background:#dbeafe;color:#1e3a8a}
.bar{height:8px;background:var(--line);border-radius:4px;overflow:hidden;margin:4px 0}.bar i{display:block;height:8px;background:var(--blue)}
.row{border-bottom:1px solid var(--line);padding:8px 0}.gap{border-left:4px solid #dc2626;padding:6px 12px;margin:10px 0;background:var(--card)}
.conf{border-left:4px solid var(--blue);padding:6px 12px;margin:10px 0;background:var(--card)}
.nf{border:1px solid #ca8a04;background:var(--midbg);color:var(--mid);padding:6px 12px;border-radius:8px;margin:10px 0}
ol.choices{padding-left:0;list-style:none}ol.choices li{padding:4px 8px;border-radius:6px;margin:2px 0}
.q{font-weight:600}.muted{color:var(--muted)}details summary{cursor:pointer;font-weight:600}
table.t{border-collapse:collapse;width:100%}table.t td,table.t th{border:1px solid var(--line);padding:4px 8px;font-size:.9em}
@media print{.card{break-inside:avoid}details{display:block}details>*{display:block}}
"""

_PAGE_CITE = re.compile(r"\(p\.\s*(\d+(?:\s*[,~\-]\s*(?:p\.\s*)?\d+)*)\)")


def esc(text) -> str:
    return html.escape(str(text or ""))


def with_pages(text) -> str:
    """이스케이프한 뒤 (p.n) 인용을 페이지 배지로."""
    return _PAGE_CITE.sub(lambda m: f'<span class="pg">p.{m.group(1)}</span>', esc(text))


def paras(text) -> str:
    parts = [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]
    return "".join(f"<p>{with_pages(p).replace(chr(10), '<br>')}</p>" for p in parts)


def page_badges(pages) -> str:
    return " ".join(f'<span class="pg">p.{int(p)}</span>' for p in pages or [])


def status_badge(status: str) -> str:
    return f'<span class="badge {STATUS_CLASS.get(status, "none")}">{esc(status)}</span>'


def _doc(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body>{body}</body></html>")


def _info(state: dict) -> str:
    mat = (state.get("material") or {}).get("name", "(자료 없음)")
    src = state.get("transcript_source")
    rec = {"audio": "녹음 포함", "paste": "대본 포함"}.get(src, "녹음·대본 없음")
    return f'<div class="info">{esc(mat)} · {esc(state.get("date", ""))} · {rec}</div>'


def _stats(items) -> str:
    return '<div class="stats">' + "".join(
        f'<div class="stat"><span class="muted">{esc(k)}</span><b>{v}</b></div>' for k, v in items) + "</div>"


def _score_by_id(state) -> dict:
    return {s["concept_id"]: s for s in state.get("scores") or []}


def reason_badges(score_row: dict) -> str:
    """같은 종류의 발화는 '강조 ×2'처럼 묶는다. 감점 신호는 줄 그은 회색."""
    groups = {}
    for r in (score_row or {}).get("reasons", []):
        label = r["label"].split(":")[0]
        g = groups.setdefault(label, {"n": 0, "neg": r["points"] < 0})
        g["n"] += 1
    out = []
    for label, g in groups.items():
        text = f"{label} ×{g['n']}" if g["n"] > 1 else label
        style = ' style="text-decoration:line-through;opacity:.7"' if g["neg"] else ""
        out.append(f'<span class="badge{" none" if g["neg"] else ""}"{style}>{esc(text)}</span>')
    return "".join(out)


def question_block(q: dict, state: dict, cid: str) -> str:
    parts = [f'<div class="muted">문제 ({esc(q["kind"])})</div><div class="q">{esc(q["question"])}</div>',
             figure_html(q.get("figure"))]
    if q["kind"] == MCQ:
        mine = (state.get("mcq_choice") or {}).get(cid)
        items = []
        for i, ch in enumerate(q.get("choices", [])):
            tag, cls = [], ""
            if i == q["answer_index"]:
                tag.append("정답")
                cls = "ok"
            if mine == i:
                tag.append("내 답")
                cls = cls or "bad"
            t = f' <b>· {" · ".join(tag)}</b>' if tag else ""
            items.append(f'<li class="{cls}">{CHOICE_MARKS[i]} {esc(ch)}{t}</li>')
        parts.append(f'<ol class="choices">{"".join(items)}</ol>')
        if mine == -1:
            parts.append('<div>내 답: <b>모르겠어요</b></div>')
        elif mine is not None and (state.get("guessed") or {}).get(cid):
            parts.append('<div class="muted">확신 없이 골랐어요</div>')
    else:
        ans = (state.get("answers") or {}).get(cid, "")
        dk = (state.get("dont_know") or {}).get(cid)
        parts.append(f'<div><span class="muted">내 답</span><br>{esc(ans) if ans and not dk else "(모르겠어요)"}</div>')
    return "".join(parts)


def grading_block(q: dict, g: dict | None) -> str:
    if not g:
        return '<div class="muted">채점하지 못했어요.</div>'
    et = f" · {esc(g['error_type'])}" if g.get("error_type") else ""
    out = [f'<div style="margin-top:8px">{status_badge(g["status"])} <b>{g["score"]}/10</b>{et}</div>',
           f'<div>{with_pages(g.get("reason", ""))}</div>']
    if q["kind"] == MCQ:
        out.append(f'<div style="margin-top:6px"><span class="muted">해설</span>{paras(q.get("explanation", ""))}</div>')
    else:
        rub = "".join(f"<li>{esc(r['point'])} ({sc}/{r['score']})</li>"
                      for r, sc in zip(q.get("rubric", []), g.get("rubric_scores", []) or [0] * 10))
        out.append(f'<div style="margin-top:6px"><span class="muted">모범 답안</span>{paras(q.get("answer", ""))}'
                   f'<ul>{rub}</ul></div>')
    out.append(f'<div class="muted">근거 {page_badges(q.get("source_pages"))}</div>')
    return "".join(out)


def explanation_block(ex: dict | None, confusion: str, fallback_pages) -> str:
    out = ['<h4 style="margin:14px 0 4px">보완 설명</h4>']
    if confusion and not (ex and ex.get("confusion_reply")):
        out.append(f'<div class="conf"><b>💬 내가 헷갈린 점</b><br>{esc(confusion)}</div>')
    if not ex:
        out.append(f'<div class="muted">설명을 만들지 않았어요. 근거 페이지: {page_badges(fallback_pages)}</div>')
        return "".join(out)
    if ex.get("my_gap"):
        out.append(f'<div class="gap"><b>내가 놓친 점</b><br>{with_pages(ex["my_gap"])}</div>')
    if confusion and ex.get("confusion_reply"):
        out.append(f'<div class="conf"><b>💬 내가 헷갈린 점에 대한 답</b><br><span class="muted">{esc(confusion)}</span>'
                   f'<br>{with_pages(ex["confusion_reply"])}</div>')
    out.append(paras(ex.get("explanation", "")))
    if ex.get("not_found"):
        note = ex.get("not_found_note") or "설명에 필요한 내용 일부가 올린 자료에 없어요."
        out.append(f'<div class="nf"><b>올린 자료에서 찾지 못함</b><br>{esc(note)}<br>'
                   f'교재 다른 장이나 수업 노트를 확인하세요.</div>')
    out.append(f'<div class="muted">다시 볼 페이지 {page_badges(ex.get("check_pages"))}</div>')
    return "".join(out)


def card(pr: dict, state: dict) -> str:
    cid = pr["concept_id"]
    q = (state.get("questions") or {}).get(cid)
    g = (state.get("grading") or {}).get(cid)
    ex = (state.get("explanations") or {}).get(cid)
    conf = (state.get("confusion") or {}).get(cid, "") if q and q["kind"] == MCQ else ""
    head = (f'<h3 style="margin:0">{pr["rank"]}. {esc(pr["name"])}</h3><div>{status_badge(pr["status"])}'
            f'<span class="badge">출제 점수 {pr["exam_pct"]}</span><span class="badge">우선순위 {pr["priority"]}</span></div>')
    body = ""
    if q:
        body += question_block(q, state, cid) + grading_block(q, g)
    sp = (q or {}).get("source_pages") or []
    body += explanation_block(ex, conf, sp)
    return f'<div class="card">{head}{body}</div>'


def study_html(state: dict) -> str:
    pri = state.get("priorities") or []
    sc = _score_by_id(state)
    counts = {a: sum(1 for p in pri if p["action"] == a) for a in ("지금 당장", "다음", "복습만")}
    body = [f"<h1>빈틈노트 공부 순서·오답노트</h1>{_info(state)}",
            f'<div class="warn">{DISCLAIMER}</div>', _stats(counts.items()), "<h2>1. 공부 순서</h2>"]
    if not pri:
        body.append("<p>우선순위 없음</p>")
    for action in ("지금 당장", "다음", "복습만"):
        rows = [p for p in pri if p["action"] == action]
        if not rows:
            continue
        body.append(f'<h3>{action} · {len(rows)}개</h3><div class="muted">{ACTION_DESC[action]}</div>')
        for p in rows:
            body.append(
                f'<div class="row"><b>{p["rank"]}. {esc(p["name"])}</b> {status_badge(p["status"])}'
                f'<span class="badge">우선순위 {p["priority"]}</span>'
                f'<div class="muted">출제 가능성 점수 {p["exam_pct"]}점</div>'
                f'<div class="bar"><i style="width:{p["exam_pct"]}%"></i></div>{reason_badges(sc.get(p["concept_id"]))}</div>')
    body.append('<p class="muted">계산식: 우선순위 = 출제 점수 × (1 − 이해도). 이해도는 앎 1.0 · 헷갈림 0.5 · 모름 0.0 · '
                '진단 안 함 0.5. 50 이상 지금 당장, 20~49 다음, 20 미만 복습만.</p>')
    questions = state.get("questions") or {}
    wrong = [p for p in pri if p["concept_id"] in questions and p["status"] in ("모름", "헷갈림")]
    right = [p for p in pri if p["concept_id"] in questions and p["status"] == "앎"]
    body.append(f"<h2>2. 오답노트 · {len(wrong)}개</h2>")
    if not questions:
        body.append("<p>진단하지 않음</p>")
    elif not wrong:
        body.append("<p>틀리거나 헷갈린 문제가 없어요.</p>")
    body.extend(card(p, state) for p in wrong)
    body.append(f"<h2>3. 맞힌 문제 · {len(right)}개</h2>")
    for p in right:
        body.append(f'<details><summary>{p["rank"]}. {esc(p["name"])}</summary>{card(p, state)}</details>')
    extra = [p for p in pri if p["concept_id"] not in questions and p["concept_id"] in (state.get("explanations") or {})]
    if extra:
        body.append("<h2>4. 진단하지 않은 개념 설명</h2>")
        body.extend(card(p, state) for p in extra)
    body.append(f'<p class="warn">{FOOTER}</p>')
    return _doc("빈틈노트 공부 순서·오답노트", "".join(body))


def note_card(i: int, n: dict, c: dict, p: dict | None, utterances: list) -> str:
    cid = n["concept_id"]
    parts = [f'<div class="card"><h3 style="margin:0">{i}. {esc(c.get("name", cid))} '
             f'<span class="badge">{esc(n["detail"])}</span></h3>']
    if p:
        parts.append(f'<div>{status_badge(p.get("status", ""))}<span class="badge">출제 점수 {p.get("exam_pct", 0)}</span>'
                     f'<span class="badge">{esc(p.get("action", ""))}</span></div>')
    parts.append(paras(n.get("summary", "")))
    if n.get("key_points"):
        parts.append("<b>핵심</b><ul>" + "".join(f"<li>{with_pages(k)}</li>" for k in n["key_points"]) + "</ul>")
    if n.get("pitfalls"):
        parts.append("<b>자주 하는 실수</b><ul>" + "".join(f"<li>{with_pages(k)}</li>" for k in n["pitfalls"]) + "</ul>")
    quotes = professor_quotes(utterances, cid, 3)
    if quotes:
        parts.append("<b>교수님 말</b><ul>" + "".join(f"<li>“{esc(u['quote'])}”</li>" for u in quotes) + "</ul>")
    parts.append(f'<div class="muted">근거 {page_badges(n.get("source_pages"))}</div></div>')
    return "".join(parts)


def notes_html(state: dict) -> str:
    notes = state.get("notes") or {}
    concepts = state.get("concepts") or []
    meta = state.get("meta_pages") or []
    pri = {p["concept_id"]: p for p in state.get("priorities") or []}
    by_id = {c["id"]: c for c in concepts}
    counts = {d: sum(1 for n in notes.values() if n["detail"] == d) for d in ("자세히", "보통", "짧게")}
    body = [f"<h1>빈틈노트 시험 대비 요약 노트</h1>{_info(state)}", f'<div class="warn">{DISCLAIMER}</div>',
            _stats(counts.items())]
    if not notes:
        body.append("<p>요약 노트 없음</p>")
    order = [cid for cid in lecture_order(concepts, meta) if cid in notes]
    for i, cid in enumerate(order, start=1):
        body.append(note_card(i, notes[cid], by_id.get(cid, {"name": cid}), pri.get(cid), state.get("utterances") or []))
    body.append(f'<p class="warn">{FOOTER}</p>')
    return _doc("빈틈노트 시험 대비 요약 노트", "".join(body))
