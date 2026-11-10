"""F10 결과 내보내기: HTML 파일 두 개. 순수 함수, 글은 모두 이스케이프, 페이지 그림 없음."""
from __future__ import annotations

import html
import re

from core.diagnose import DONT_KNOW, MCQ
from core.figure import figure_html
from core.note import lecture_order, professor_quotes
from core.priority import ACTIONS
from core.score import badges

DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다."
LAST_LINE = "이 결과는 자료와 녹음의 신호를 규칙대로 더한 것으로, 실제 출제를 보장하지 않습니다."
ACTION_DESC = {
    "지금 당장": "출제 점수가 높은데 아직 모르는 개념. 여기부터 보세요.",
    "다음": "지금 당장 다음으로 볼 개념.",
    "복습만": "이미 알거나 출제 점수가 낮은 개념. 가볍게 훑어보세요.",
}
STATUS_CLASS = {"앎": "ok", "헷갈림": "mid", "모름": "bad", "진단 안 함": "none"}

CSS = """
:root{--bg:#ffffff;--fg:#1f2937;--muted:#64748b;--card:#f8fafc;--line:#e2e8f0;--blue:#2563eb;
--ok:#15803d;--okbg:#dcfce7;--mid:#a16207;--midbg:#fef9c3;--bad:#b91c1c;--badbg:#fee2e2;--nonebg:#e2e8f0}
@media (prefers-color-scheme: dark){:root{--bg:#0f172a;--fg:#e2e8f0;--muted:#94a3b8;--card:#1e293b;--line:#334155;
--okbg:#14532d;--ok:#bbf7d0;--midbg:#713f12;--mid:#fef08a;--badbg:#7f1d1d;--bad:#fecaca;--nonebg:#334155}}
body{background:var(--bg);color:var(--fg);font-family:-apple-system,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;
font-size:16px;line-height:1.75;max-width:860px;margin:0 auto;padding:24px 16px}
h1{font-size:1.6em;margin:0 0 4px}h2{font-size:1.25em;margin:32px 0 8px;border-bottom:2px solid var(--line);padding-bottom:4px}
h3{font-size:1.05em;margin:18px 0 6px}.info{color:var(--muted);font-size:.9em}
.warn{border:1px solid var(--line);border-left:4px solid var(--blue);background:var(--card);padding:8px 12px;border-radius:6px;margin:12px 0}
.metrics{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.metric{flex:1;min-width:120px;border:1px solid var(--line);border-radius:8px;padding:8px 12px;background:var(--card)}
.metric b{display:block;font-size:1.5em}.row{border:1px solid var(--line);border-radius:8px;padding:8px 12px;margin:6px 0;background:var(--card)}
.bar{display:inline-block;height:8px;background:var(--line);border-radius:4px;width:120px;vertical-align:middle}
.bar i{display:block;height:8px;background:var(--blue);border-radius:4px}
.b{display:inline-block;font-size:.8em;padding:1px 8px;border-radius:10px;margin:2px 4px 2px 0;background:var(--nonebg)}
.b.ok{background:var(--okbg);color:var(--ok)}.b.mid{background:var(--midbg);color:var(--mid)}.b.bad{background:var(--badbg);color:var(--bad)}
.b.minus{text-decoration:line-through;color:var(--muted)}.pg{display:inline-block;font-size:.78em;padding:0 6px;border-radius:8px;background:#dbeafe;color:#1e40af}
.card{border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:12px 0;background:var(--card)}
.gap{border-left:4px solid #dc2626;padding:4px 10px;margin:8px 0}.conf{border-left:4px solid #2563eb;padding:4px 10px;margin:8px 0}
.nf{border:1px solid #eab308;background:var(--midbg);color:var(--mid);padding:6px 10px;border-radius:6px;margin:8px 0}
.choice{margin:2px 0}.choice.right{color:var(--ok);font-weight:600}.choice.mine{color:var(--bad)}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}
@media print{details{display:block}details>*{display:block}body{max-width:none}}
"""


def esc(s) -> str:
    return html.escape("" if s is None else str(s))


_PG = re.compile(r"\(p\.\s*(\d+(?:\s*[,~\-]\s*(?:p\.\s*)?\d+)*)\)")


def rich(text: str | None) -> str:
    """이스케이프한 뒤 (p.n)을 페이지 배지로, 빈 줄을 문단으로."""
    out = []
    for para in re.split(r"\n\s*\n", (text or "").strip()):
        if not para.strip():
            continue
        e = esc(para).replace("\n", "<br>")
        e = _PG.sub(lambda m: f'<span class="pg">p.{m.group(1)}</span>', e)
        out.append(f"<p>{e}</p>")
    return "".join(out)


def pages_badges(pages) -> str:
    return " ".join(f'<span class="pg">p.{int(p)}</span>' for p in pages or [])


def _bar(v: int) -> str:
    v = max(0, min(int(v), 100))
    return f'<span class="bar"><i style="width:{v}%"></i></span>'


def _head(title: str, state: dict) -> str:
    src = {"audio": "녹음 받아쓰기 포함", "paste": "대본 포함"}.get(state.get("transcript_source"), "녹음·대본 없음")
    return (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'><title>{esc(title)}</title>"
            f"<style>{CSS}</style></head><body><h1>{esc(title)}</h1>"
            f"<div class='info'>{esc(state.get('material_name', ''))} · {esc(state.get('date', ''))} · {esc(src)}</div>"
            f"<div class='warn'>{esc(DISCLAIMER)}</div>")


def _metrics(items) -> str:
    return "<div class='metrics'>" + "".join(f"<div class='metric'>{esc(k)}<b>{v}</b></div>" for k, v in items) + "</div>"


def _status_badge(status: str) -> str:
    return f'<span class="b {STATUS_CLASS.get(status, "none")}">{esc(status)}</span>'


def _answer_block(q: dict, g: dict, ans: dict) -> str:
    parts = []
    if q["kind"] == MCQ:
        ch = ans.get("choice")
        for i, c in enumerate(q["choices"]):
            cls, mark = "choice", ""
            if i == q["answer_index"]:
                cls += " right"
                mark = " ✔ 정답"
            if ch == i and i != q["answer_index"]:
                cls += " mine"
                mark = " ✘ 내 답"
            elif ch == i:
                mark += " · 내 답"
            parts.append(f"<div class='{cls}'>{'①②③④'[i] if i < 4 else i + 1} {esc(c)}{esc(mark)}</div>")
        if ch == DONT_KNOW:
            parts.append("<div class='choice mine'>내 답: 모르겠어요</div>")
        if ans.get("guessed"):
            parts.append("<div class='info'>확신 없이 골랐어요</div>")
    else:
        mine = "모르겠어요" if ans.get("dont_know") else (ans.get("answer") or "(빈 답)")
        parts.append(f"<div><b>내 답</b></div>{rich(mine)}")
    et = f" · {esc(g.get('error_type'))}" if g.get("error_type") else ""
    parts.append(f"<div><b>채점</b> {g['score']}/10{et}</div>{rich(g.get('reason', ''))}")
    if q["kind"] == MCQ:
        parts.append(f"<div><b>해설</b></div>{rich(q.get('explanation', ''))}")
    else:
        parts.append(f"<div><b>모범 답안</b></div>{rich(q.get('answer', ''))}")
        if q.get("rubric"):
            rs = g.get("rubric_scores") or []
            items = "".join(
                f"<li>{esc(r['point'])} ({rs[i] if i < len(rs) else '-'}/{r['score']})</li>" for i, r in enumerate(q["rubric"]))
            parts.append(f"<ul>{items}</ul>")
    return "".join(parts)


def _confusion_block(written: str, reply: str | None) -> str:
    if not written:
        return ""
    if reply:
        return (f"<div class='conf'><b>💬 내가 헷갈린 점에 대한 답</b><div class='info'>내가 적은 글: {esc(written)}</div>"
                f"{rich(reply)}</div>")
    return f"<div class='conf'><b>💬 내가 헷갈린 점</b><div>{esc(written)}</div></div>"


def _explain_block(ex: dict | None, written: str, fallback_pages) -> str:
    if not ex:
        return _confusion_block(written, None) + f"<div class='info'>근거 페이지 {pages_badges(fallback_pages)}</div>"
    parts = ["<h3>보완 설명</h3>"]
    if ex.get("my_gap"):
        parts.append(f"<div class='gap'><b>내가 놓친 점</b> {esc(ex['my_gap'])}</div>")
    parts.append(_confusion_block(written, ex.get("confusion_reply")))
    parts.append(rich(ex.get("explanation", "")))
    if ex.get("not_found"):
        parts.append(f"<div class='nf'>올린 자료에서 찾지 못함 · {esc(ex.get('not_found_note') or '')} "
                     f"교재 다른 장이나 수업 노트를 확인하세요.</div>")
    parts.append(f"<div class='info'>다시 볼 페이지 {pages_badges(ex.get('check_pages'))}</div>")
    return "".join(parts)


def _card(p: dict, state: dict) -> str:
    cid = p["concept_id"]
    q = state.get("questions", {}).get(cid)
    g = state.get("grading", {}).get(cid)
    ans = {
        "answer": state.get("answers", {}).get(cid, ""),
        "dont_know": state.get("dont_know", {}).get(cid, False),
        "choice": state.get("mcq_choice", {}).get(cid),
        "guessed": state.get("guessed", {}).get(cid, False),
    }
    written = state.get("confusion", {}).get(cid, "") if q and q["kind"] == MCQ and ans["guessed"] else ""
    ex = state.get("explanations", {}).get(cid)
    head = (f"<div class='card'><h3>{p['rank']}. {esc(p['name'])}</h3>{_status_badge(p['status'])}"
            f"<span class='b'>출제 점수 {p['exam_pct']}</span><span class='b'>우선순위 {p['priority']}</span>")
    body = ""
    if q and g:
        body += f"<div><b>Q. </b>{esc(q['question'])}</div>{figure_html(q.get('figure'))}{_answer_block(q, g, ans)}"
    body += _explain_block(ex, written, (q or {}).get("source_pages", []))
    return head + body + "</div>"


def study_html(state: dict) -> str:
    """① 공부 순서·오답노트."""
    pr = state.get("priorities") or []
    scores = {s["concept_id"]: s for s in state.get("scores") or []}
    counts = [(a, sum(1 for p in pr if p["action"] == a)) for a in ACTIONS]
    out = [_head("빈틈노트 공부 순서·오답노트", state), _metrics(counts), "<h2>1. 공부 순서</h2>"]
    if not pr:
        out.append("<p>우선순위 없음</p>")
    for a in ACTIONS:
        rows = [p for p in pr if p["action"] == a]
        if not rows:
            continue
        out.append(f"<h3>{esc(a)} · {len(rows)}개</h3><div class='info'>{esc(ACTION_DESC[a])}</div>")
        for p in rows:
            bs = "".join(f'<span class="b{" minus" if minus else ""}">{esc(t)}</span>'
                         for t, minus in badges(scores.get(p["concept_id"], {})))
            out.append(f"<div class='row'><b>{p['rank']}. {esc(p['name'])}</b> {_status_badge(p['status'])}<br>"
                       f"출제 점수 {_bar(p['exam_pct'])} {p['exam_pct']}점 · 우선순위 {p['priority']}<br>{bs}</div>")
    out.append("<p class='info'>우선순위 = 출제 점수 × (1 − 이해도). 이해도: 앎 1.0 · 헷갈림 0.5 · 모름 0.0 · 진단 안 함 0.5. "
               "50 이상 지금 당장, 20~49 다음, 20 미만 복습만.</p>")

    graded = state.get("grading") or {}
    out.append("<h2>2. 오답노트</h2>")
    wrong = [p for p in pr if p["concept_id"] in graded and p["status"] in ("모름", "헷갈림")]
    if not graded:
        out.append("<p>진단하지 않음</p>")
    elif not wrong:
        out.append("<p>틀리거나 헷갈린 문제가 없어요.</p>")
    for p in wrong:
        out.append(_card(p, state))
    right = [p for p in pr if p["concept_id"] in graded and p["status"] == "앎"]
    if right:
        out.append(f"<h2>3. 맞힌 문제 · {len(right)}개</h2><details><summary>눌러서 펼치기</summary>")
        out.extend(_card(p, state) for p in right)
        out.append("</details>")
    extra = [p for p in pr if p["concept_id"] not in graded and p["concept_id"] in (state.get("explanations") or {})]
    if extra:
        out.append("<h2>4. 진단하지 않은 개념 설명</h2>")
        out.extend(_card(p, state) for p in extra)
    out.append(f"<p class='info'>{esc(LAST_LINE)}</p></body></html>")
    return "".join(out)


def notes_html(state: dict) -> str:
    """② 시험 대비 요약 노트."""
    notes = state.get("notes") or {}
    concepts = state.get("concepts") or []
    prio = {p["concept_id"]: p for p in state.get("priorities") or []}
    counts = [(d, sum(1 for n in notes.values() if n["detail"] == d)) for d in ("자세히", "보통", "짧게")]
    out = [_head("빈틈노트 시험 대비 요약 노트", state), _metrics(counts)]
    if not notes:
        out.append("<p>요약 노트 없음</p>")
    by_id = {c["id"]: c for c in concepts}
    for i, cid in enumerate(lecture_order(concepts, state.get("meta") or []), 1):
        n = notes.get(cid)
        c = by_id.get(cid)
        if not n or not c:
            continue
        p = prio.get(cid, {})
        out.append(f"<div class='card'><h3>{i}. {esc(c['name'])} <span class='b'>{esc(n['detail'])}</span></h3>")
        if p:
            out.append(f"{_status_badge(p.get('status', ''))}<span class='b'>출제 점수 {p.get('exam_pct', 0)}</span>"
                       f"<span class='b'>{esc(p.get('action', ''))}</span>")
        out.append(rich(n.get("summary", "")))
        if n.get("key_points"):
            out.append("<div><b>핵심</b></div><ul>" + "".join(f"<li>{rich(k)[3:-4]}</li>" for k in n["key_points"]) + "</ul>")
        if n.get("pitfalls"):
            out.append("<div><b>자주 하는 실수</b></div><ul>" + "".join(f"<li>{rich(k)[3:-4]}</li>" for k in n["pitfalls"]) + "</ul>")
        qs = professor_quotes(cid, state.get("utterances") or [], 3)
        if qs and n["detail"] != "짧게":
            out.append("<div><b>교수님 말</b></div><ul>" + "".join(f"<li>“{esc(u['quote'])}”</li>" for u in qs) + "</ul>")
        out.append(f"<div class='info'>근거 페이지 {pages_badges(n.get('source_pages'))}</div></div>")
    out.append(f"<p class='info'>{esc(LAST_LINE)}</p></body></html>")
    return "".join(out)
