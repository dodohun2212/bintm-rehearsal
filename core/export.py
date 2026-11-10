"""F10 내려받는 HTML 파일 두 개. 외부 호출이 없는 순수 함수. 글은 모두 이스케이프, 페이지 그림은 넣지 않는다."""
from __future__ import annotations

import datetime as _dt
import html
import re

from core.diagnose import MCQ
from core.figure import figure_html
from core.guard import today_kst
from core.note import DETAILED, NORMAL, SHORT, lecture_order, professor_quotes
from core.priority import NEXT, NOW, REVIEW, group

DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다."
LAST_LINE = "이 결과는 자료와 녹음의 신호를 규칙대로 더한 것으로, 실제 출제를 보장하지 않습니다."
FORMULA = "우선순위 = 출제 점수 × (1 − 이해도) · 이해도: 앎 1.0, 헷갈림 0.5, 모름 0.0, 진단 안 함 0.5"
CHOICE_MARKS = ("①", "②", "③", "④")

CSS = """
:root{--bg:#ffffff;--fg:#1d2433;--muted:#5f6b7a;--line:#d9dee7;--card:#f7f9fc;--blue:#2f5bd3;
--ok:#1f8a4c;--ok-bg:#e6f5ec;--mid:#a86b00;--mid-bg:#fff4dc;--bad:#c43d3d;--bad-bg:#fdeaea;--info-bg:#eaf1ff}
@media (prefers-color-scheme: dark){:root{--bg:#141922;--fg:#e6eaf0;--muted:#a3adbb;--line:#2e3747;--card:#1b2230;
--blue:#7aa2ff;--ok:#5cd08d;--ok-bg:#16301f;--mid:#f0b54a;--mid-bg:#33290f;--bad:#ff8080;--bad-bg:#3a1a1a;--info-bg:#1a2742}}
body{background:var(--bg);color:var(--fg);font-family:"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;
font-size:16px;line-height:1.75;max-width:860px;margin:0 auto;padding:24px 16px}
h1{font-size:1.6rem;margin:.2em 0}h2{font-size:1.25rem;border-bottom:2px solid var(--line);padding-bottom:4px;margin-top:2em}
h3{font-size:1.05rem;margin:1.2em 0 .4em}.info{color:var(--muted);font-size:.92rem}
.warn{border:1px solid var(--line);border-left:4px solid var(--mid);background:var(--mid-bg);padding:10px 14px;border-radius:8px;margin:12px 0}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}.stat{flex:1;min-width:110px;border:1px solid var(--line);border-radius:10px;padding:8px 12px;background:var(--card)}
.stat b{display:block;font-size:1.5rem}.row{border:1px solid var(--line);border-radius:10px;padding:8px 12px;margin:6px 0;background:var(--card)}
.bar{background:var(--line);border-radius:6px;height:8px;width:160px;display:inline-block;vertical-align:middle;margin:0 6px}
.bar i{display:block;height:8px;border-radius:6px;background:var(--blue)}
.badge{display:inline-block;font-size:.8rem;border:1px solid var(--line);border-radius:999px;padding:0 8px;margin:2px 2px;white-space:nowrap}
.neg{text-decoration:line-through;color:var(--muted)}.pg{display:inline-block;font-size:.78rem;background:var(--info-bg);color:var(--blue);border-radius:6px;padding:0 6px;margin:0 2px}
.st-앎{background:var(--ok-bg);color:var(--ok)}.st-헷갈림{background:var(--mid-bg);color:var(--mid)}.st-모름{background:var(--bad-bg);color:var(--bad)}
.card{border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin:14px 0;background:var(--card)}
.q{font-size:1.05rem;font-weight:600}.choice{margin:2px 0}.correct{color:var(--ok);font-weight:600}.mine{color:var(--bad);font-weight:600}
.gap{border-left:4px solid var(--bad);background:var(--bad-bg);padding:8px 12px;border-radius:6px;margin:8px 0}
.conf{border-left:4px solid var(--blue);background:var(--info-bg);padding:8px 12px;border-radius:6px;margin:8px 0}
.nf{border-left:4px solid var(--mid);background:var(--mid-bg);padding:8px 12px;border-radius:6px;margin:8px 0}
.figure{margin:8px 0}.fig-cap{font-size:.85rem;color:var(--muted)}table{border-collapse:collapse;margin:6px 0}
td,th{border:1px solid var(--line);padding:3px 8px;text-align:center}.fig-array .idx th{color:var(--muted);font-weight:400}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}.foot{margin-top:2em;color:var(--muted);font-size:.9rem}
@media print{body{max-width:none}.card,.row{break-inside:avoid}details{display:block}}
"""

_PCITE = re.compile(r"\(\s*(p\.\s*\d+(?:\s*[,·~\-–]\s*(?:p\.\s*)?\d+)*)\s*\)")


def esc(text) -> str:
    return html.escape("" if text is None else str(text))


def page_badges(pages) -> str:
    return "".join(f'<span class="pg">p.{int(n)}</span>' for n in pages or [])


def rich(text: str | None) -> str:
    """이스케이프한 뒤 (p.n) 인용을 페이지 배지로, 빈 줄로 문단을 나눈다."""
    out = []
    for para in re.split(r"\n\s*\n", text or ""):
        if not para.strip():
            continue
        e = esc(para.strip()).replace("\n", "<br>")
        e = _PCITE.sub(lambda m: page_badges(re.findall(r"\d+", m.group(1))), e)
        out.append(f"<p>{e}</p>")
    return "".join(out)


def _doc(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{esc(title)}</title><style>{CSS}</style></head><body>{body}</body></html>")


def _info_line(state: dict, today: str) -> str:
    name = (state.get("material") or {}).get("name") or "자료 없음"
    src = {"audio": "녹음 포함", "paste": "대본 포함"}.get(state.get("transcript_source"), "녹음·대본 없음")
    return f'<div class="info">{esc(name)} · {esc(today)} · {src}</div>'


def _status_badge(status: str) -> str:
    return f'<span class="badge st-{esc(status)}">{esc(status)}</span>'


def _reason_badges(score: dict | None) -> str:
    if not score:
        return ""
    from core.score import badges
    return "".join(f'<span class="badge{" neg" if neg else ""}">{esc(t)}</span>' for t, neg in badges(score))


def _question_block(q: dict, state: dict, cid: str, g: dict | None, show_conf: bool = True) -> str:
    """show_conf=False면 헷갈린 점 줄을 빼고 보완 설명 쪽에서 한 번만 보인다."""
    parts = [f'<div class="q">{esc(q["question"])}</div>', figure_html(q.get("figure"))]
    conf = (state.get("confusion") or {}).get(cid, "")
    if q["kind"] == MCQ:
        mine = (state.get("mcq_choice") or {}).get(cid)
        for i, c in enumerate(q["choices"]):
            cls, tag = "choice", ""
            if i == q["answer_index"]:
                cls, tag = "choice correct", " ✔ 정답"
            if i == mine and i != q["answer_index"]:
                cls, tag = "choice mine", " ✘ 내 답"
            elif i == mine:
                tag += " · 내 답"
            parts.append(f'<div class="{cls}">{CHOICE_MARKS[i]} {esc(c)}{tag}</div>')
        if mine == -1:
            parts.append('<div class="choice mine">내 답: 모르겠어요</div>')
        if (state.get("guessed") or {}).get(cid):
            parts.append('<div class="info">확신 없이 골랐어요</div>')
    else:
        dk = (state.get("dont_know") or {}).get(cid)
        ans = "모르겠어요" if dk else (state.get("answers") or {}).get(cid, "")
        parts.append(f'<div><b>내 답</b><div>{esc(ans) or "(빈 답)"}</div></div>')
    if g:
        et = f' · {esc(g["error_type"])}' if g.get("error_type") else ""
        parts.append(f'<div><b>채점</b> {_status_badge(g["status"])} {g["score"]}/10{et} — {esc(g.get("reason"))}</div>')
    if q["kind"] == MCQ:
        parts.append(f'<div><b>해설</b>{rich(q.get("explanation"))}</div>')
    else:
        rub = "".join(f"<li>{esc(r['point'])} ({r['score']}점)</li>" for r in q.get("rubric", []))
        parts.append(f'<div><b>모범 답안</b>{rich(q.get("answer"))}<ul>{rub}</ul></div>')
    parts.append(f'<div class="info">문제 근거 {page_badges(q.get("source_pages"))}</div>')
    if show_conf and conf.strip():
        parts.append(f'<div class="info">💬 내가 헷갈린 점: {esc(conf)}</div>')
    return "".join(parts)


def explanation_block(e: dict | None, confusion: str = "", fallback_pages=None) -> str:
    if not e:
        return f'<div class="info">근거 페이지 {page_badges(fallback_pages)}</div>' if fallback_pages else ""
    parts = ['<h3>보완 설명</h3>']
    if e.get("my_gap"):
        parts.append(f'<div class="gap"><b>내가 놓친 점</b> {esc(e["my_gap"])}</div>')
    if confusion.strip() and e.get("confusion_reply"):
        parts.append(f'<div class="conf"><b>💬 내가 헷갈린 점에 대한 답</b>'
                     f'<div class="info">내가 적은 글: {esc(confusion)}</div>{rich(e["confusion_reply"])}</div>')
    elif confusion.strip():  # 답이 없으면 적은 글만
        parts.append(f'<div class="info">💬 내가 헷갈린 점: {esc(confusion)}</div>')
    parts.append(rich(e.get("explanation")))
    if e.get("not_found"):
        parts.append(f'<div class="nf"><b>올린 자료에서 찾지 못함</b> {esc(e.get("not_found_note") or "")}'
                     f' 교재 다른 장이나 수업 노트를 확인하세요.</div>')
    parts.append(f'<div class="info">다시 볼 페이지 {page_badges(e.get("check_pages"))}</div>')
    return "".join(parts)


def _card(p: dict, state: dict, score: dict | None) -> str:
    cid = p["concept_id"]
    q = (state.get("questions") or {}).get(cid)
    g = (state.get("grading") or {}).get(cid)
    e = (state.get("explanations") or {}).get(cid)
    conf = (state.get("confusion") or {}).get(cid, "") or ""
    head = (f'<div><b>{p["rank"]}. {esc(p["name"])}</b> {_status_badge(p["status"])}'
            f'<span class="badge">출제 점수 {p["exam_pct"]}</span><span class="badge">우선순위 {p["priority"]}</span></div>')
    body = _question_block(q, state, cid, g, show_conf=not e) if q else ""
    pages = (score or {}).get("body_pages") or (score or {}).get("pages")
    return f'<div class="card">{head}{body}{explanation_block(e, conf, pages)}</div>'


def study_html(state: dict, today: str | None = None) -> str:
    """① 공부 순서·오답노트."""
    today = today or today_kst().isoformat()
    pr = state.get("priorities") or []
    scores = {s["concept_id"]: s for s in state.get("scores") or []}
    groups = group(pr)
    b = [f"<h1>빈틈노트 공부 순서·오답노트</h1>", _info_line(state, today),
         f'<div class="warn">{DISCLAIMER}</div>',
         '<div class="stats">' + "".join(f'<div class="stat">{k} <b>{len(groups[k])}</b></div>'
                                         for k in (NOW, NEXT, REVIEW)) + "</div>",
         "<h2>1. 공부 순서</h2>"]
    if not pr:
        b.append("<p>우선순위 없음</p>")
    for k, desc in ((NOW, "여기부터 보세요"), (NEXT, "지금 당장 다음에"), (REVIEW, "시간이 남으면")):
        if not groups[k]:
            continue
        b.append(f"<h3>{k} · {desc}</h3>")
        for p in groups[k]:
            s = scores.get(p["concept_id"])
            b.append(f'<div class="row"><b>{p["rank"]}. {esc(p["name"])}</b> {_status_badge(p["status"])}<br>'
                     f'<span class="bar"><i style="width:{p["exam_pct"]}%"></i></span>'
                     f'출제 가능성 점수 {p["exam_pct"]}점 · 우선순위 {p["priority"]}<br>{_reason_badges(s)}</div>')
    if pr:
        b.append(f'<div class="info">{FORMULA}</div>')

    diagnosed = [p for p in pr if p["concept_id"] in (state.get("grading") or {})]
    wrong = [p for p in diagnosed if p["status"] in ("모름", "헷갈림")]
    right = [p for p in diagnosed if p["status"] == "앎"]
    b.append("<h2>2. 오답노트</h2>")
    if not diagnosed:
        b.append("<p>진단하지 않음</p>")
    elif not wrong:
        b.append("<p>틀리거나 헷갈린 문제가 없어요.</p>")
    for p in wrong:
        b.append(_card(p, state, scores.get(p["concept_id"])))
    if right:
        b.append(f"<h2>3. 맞힌 문제 · {len(right)}개</h2><details><summary>눌러서 펼치기</summary>")
        for p in right:
            b.append(_card(p, state, scores.get(p["concept_id"])))
        b.append("</details>")
    extra = [p for p in pr if p["concept_id"] not in (state.get("grading") or {})
             and p["concept_id"] in (state.get("explanations") or {})]
    if extra:
        b.append("<h2>4. 진단하지 않은 개념 설명</h2>")
        for p in extra:
            b.append(_card(p, state, scores.get(p["concept_id"])))
    b.append(f'<div class="foot">{LAST_LINE}</div>')
    return _doc("빈틈노트 공부 순서·오답노트", "".join(b))


def notes_html(state: dict, today: str | None = None) -> str:
    """② 시험 대비 요약 노트 (요약 노트만)."""
    today = today or today_kst().isoformat()
    notes = state.get("notes") or {}
    concepts = {c["id"]: c for c in state.get("concepts") or []}
    pr = {p["concept_id"]: p for p in state.get("priorities") or []}
    b = ["<h1>빈틈노트 시험 대비 요약 노트</h1>", _info_line(state, today), f'<div class="warn">{DISCLAIMER}</div>']
    if not notes:
        b.append("<p>요약 노트 없음</p>")
    else:
        counts = {DETAILED: 0, NORMAL: 0, SHORT: 0}
        for n in notes.values():
            counts[n["detail"]] = counts.get(n["detail"], 0) + 1
        b.append('<div class="stats">' + "".join(f'<div class="stat">{k} <b>{v}</b></div>'
                                                for k, v in counts.items()) + "</div>")
        order = lecture_order(list(concepts.values()), state.get("meta_pages") or [])
        for i, cid in enumerate([c for c in order if c in notes or c in pr], 1):
            c = concepts.get(cid, {"name": cid})
            n = notes.get(cid)
            p = pr.get(cid, {})
            badges_ = (f'<span class="badge">{esc(n["detail"]) if n else "짧게"}</span>'
                       f'<span class="badge">출제 점수 {p.get("exam_pct", 0)}</span>'
                       + (_status_badge(p["status"]) if p.get("status") else ""))
            parts = [f'<div class="note-card card"><div><b>{i}. {esc(c["name"])}</b> {badges_}</div>']
            if n:
                parts.append(rich(n.get("summary")))
                if n.get("key_points"):
                    parts.append("<b>핵심</b><ul>" + "".join(f"<li>{rich(k)[3:-4]}</li>" for k in n["key_points"]) + "</ul>")
                if n.get("pitfalls"):
                    parts.append("<b>자주 하는 실수</b><ul>" + "".join(f"<li>{rich(k)[3:-4]}</li>" for k in n["pitfalls"]) + "</ul>")
            else:
                parts.append(f"<p>{esc(c.get('summary', ''))}</p><div class='info'>(요약 노트를 만들지 못해 한 줄 요약으로 대신)</div>")
            quotes = professor_quotes(cid, state.get("utterances") or [])
            if quotes:
                parts.append("<b>교수님 말</b><ul>" + "".join(f"<li>“{esc(q['quote'])}”</li>" for q in quotes) + "</ul>")
            parts.append(f'<div class="info">근거 페이지 {page_badges((n or {}).get("source_pages") or c.get("pages", [])[:2])}</div></div>')
            b.append("".join(parts))
    b.append(f'<div class="foot">{LAST_LINE}</div>')
    return _doc("빈틈노트 시험 대비 요약 노트", "".join(b))


def file_names(today: str | None = None) -> tuple[str, str]:
    today = today or today_kst().isoformat()
    return f"빈틈노트_공부순서_오답노트_{today}.html", f"빈틈노트_요약노트_{today}.html"
