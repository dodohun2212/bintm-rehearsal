"""F10 HTML 결과 파일 두 개: study_html(공부 순서·오답노트), notes_html(요약 노트). 순수 함수.

페이지 그림은 넣지 않는다. 모든 글은 이스케이프한다. 인터넷 없이도 열린다.
"""
from __future__ import annotations

from datetime import date

from core.diagnose import MCQ
from core.figure import figure_html
from core.guard import kst_today
from core.html import (CSS, DISCLAIMER, FOOTER, action_badge, badge, bar, esc, explanation_html, note_html,
                       question_review_html, signal_badges, status_badge)
from core.note import detail_level, lecture_order, short_note
from core.utterances import professor_quotes

DOC_CSS = """
:root{color-scheme:light dark}
body{font-family:-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",sans-serif;max-width:860px;
  margin:24px auto;padding:0 16px;font-size:16.5px;line-height:1.75;color:#111827;background:#fff}
h1{font-size:1.6em;margin:.2em 0}h2{margin-top:1.8em;border-bottom:2px solid #2563eb;padding-bottom:4px}
h3{margin:.3em 0}
.info{color:#6b7280;font-size:.92em}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}
.stat{flex:1;min-width:110px;border:1px solid #d0d7e2;border-radius:10px;padding:8px 12px}
.stat b{font-size:1.5em;display:block}
.row{display:grid;grid-template-columns:2.2em 1fr 120px;gap:8px;align-items:center;padding:6px 0;
  border-bottom:1px solid #e5e7eb}
details{margin:10px 0}summary{cursor:pointer;font-weight:600}
.foot{margin-top:2em;color:#6b7280;font-size:.9em;border-top:1px solid #e5e7eb;padding-top:8px}
@media (prefers-color-scheme: dark){body{background:#0f172a;color:#e5e7eb}.info,.foot{color:#9ca3af}
  .bt-card{border-color:#334155}.row{border-color:#334155}.stat{border-color:#334155}}
@media print{details{display:block}details>*{display:block}.bt-card{break-inside:avoid}}
"""


def _ans(state: dict, cid: str) -> dict:
    return {"answer": (state.get("answers") or {}).get(cid, ""),
            "dont_know": bool((state.get("dont_know") or {}).get(cid)),
            "mcq_choice": (state.get("mcq_choice") or {}).get(cid),
            "guessed": bool((state.get("guessed") or {}).get(cid)),
            "confusion": (state.get("confusion") or {}).get(cid, "")
            if (state.get("guessed") or {}).get(cid) else ""}


def _doc(title: str, body: str) -> str:
    return (f'<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title>'
            f"<style>{CSS}{DOC_CSS}</style></head><body>{body}</body></html>")


def _head(state: dict, title: str, today: date) -> str:
    name = (state.get("material") or {}).get("name", "(자료 없음)")
    src = state.get("transcript_source")
    rec = "녹음 받아쓰기 포함" if src == "audio" else ("대본 포함" if src == "paste" or state.get("transcript")
                                                      else "녹음·대본 없음")
    return (f"<h1>{esc(title)}</h1><div class='info'>{esc(name)} · {today.isoformat()} · {esc(rec)}</div>"
            f"<div class='bt-warn'>⚠️ {esc(DISCLAIMER)}</div>")


def _stats(pairs) -> str:
    return "<div class='stats'>" + "".join(f"<div class='stat'><b>{n}</b>{esc(k)}</div>" for k, n in pairs) + "</div>"


def _card(state: dict, p: dict, smap: dict) -> str:
    cid = p["concept_id"]
    q = (state.get("questions") or {}).get(cid)
    g = (state.get("grading") or {}).get(cid)
    ex = (state.get("explanations") or {}).get(cid)
    kind = q.get("kind") if q else ""
    head = (f"<h3>{p['rank']}. {esc(p['name'])}</h3><div>{status_badge(p['status'])}"
            f"{badge('출제 점수 ' + str(p['exam_pct']))}{badge('우선순위 ' + str(p['priority']))}"
            f"{badge(kind) if kind else ''}</div>")
    review = question_review_html(q, g, _ans(state, cid), figure_html(q.get("figure")) if q else "")
    return (f"<div class='bt-card'>{head}<div style='margin-top:8px'>{review}</div>"
            f"<h4>보완 설명</h4>{explanation_html(ex)}</div>")


def study_html(state: dict, today: date | None = None) -> str:
    """① 공부 순서·오답노트."""
    today = today or kst_today()
    prios = state.get("priorities") or []
    scores = (state.get("scores") or {}).get("scores", []) if isinstance(state.get("scores"), dict) else []
    smap = {r["concept_id"]: r for r in scores}
    grading = state.get("grading") or {}
    parts = [_head(state, "빈틈노트 공부 순서·오답노트", today)]
    groups = {a: [p for p in prios if p["action"] == a] for a in ("지금 당장", "다음", "복습만")}
    parts.append(_stats([(k, len(v)) for k, v in groups.items()]))

    parts.append("<h2>1. 공부 순서</h2>")
    if not prios:
        parts.append("<p>우선순위 없음</p>")
    else:
        parts.append("<p class='bt-muted'>우선순위 = 출제 점수 × (1 − 이해도). 이해도: 앎 1.0 · 헷갈림 0.5 · 모름 0 · "
                     "진단 안 함 0.5. 50 이상 지금 당장, 20~49 다음, 20 미만 복습만.</p>")
        for act, items in groups.items():
            if not items:
                continue
            parts.append(f"<h3>{action_badge(act)} {len(items)}개</h3>")
            for p in items:
                reasons = smap.get(p["concept_id"], {}).get("reasons", [])
                parts.append(f"<div class='row'><b>{p['rank']}</b><div><b>{esc(p['name'])}</b> "
                             f"{status_badge(p['status'])}{badge('우선순위 ' + str(p['priority']))}"
                             f"<div>{signal_badges(reasons)}</div></div>"
                             f"<div>{bar(p['exam_pct'])}<span class='bt-muted'>출제 점수 {p['exam_pct']}</span></div></div>")

    parts.append("<h2>2. 오답노트</h2>")
    wrong = [p for p in prios if p["concept_id"] in grading and p["status"] in ("모름", "헷갈림")]
    right = [p for p in prios if p["concept_id"] in grading and p["status"] == "앎"]
    if not grading:
        parts.append("<p>진단하지 않음</p>")
    elif not wrong:
        parts.append("<p>틀리거나 헷갈린 문제가 없어요.</p>")
    for p in wrong:
        parts.append(_card(state, p, smap))

    parts.append(f"<h2>3. 맞힌 문제 · {len(right)}개</h2>")
    if right:
        parts.append("<details><summary>눌러서 펼치기</summary>" + "".join(_card(state, p, smap) for p in right)
                     + "</details>")
    else:
        parts.append("<p class='bt-muted'>없음</p>")

    extra = [p for p in prios if p["concept_id"] not in grading and (state.get("explanations") or {}).get(p["concept_id"])]
    if extra:
        parts.append("<h2>4. 진단하지 않은 개념 설명</h2>")
        for p in extra:
            parts.append(f"<div class='bt-card'><h3>{esc(p['name'])}</h3>{status_badge(p['status'])}"
                         f"{explanation_html(state['explanations'][p['concept_id']])}</div>")
    parts.append(f"<div class='foot'>{esc(FOOTER)}</div>")
    return _doc("빈틈노트 공부 순서·오답노트", "".join(parts))


def note_rows(state: dict) -> list[tuple[dict, str, dict | None]]:
    """강의 순서대로 (개념, 자세한 정도, 노트). 노트가 없고 '짧게'면 한 줄 요약으로 채운다."""
    concepts = state.get("concepts") or []
    meta = state.get("meta_pages") or []
    prios = {p["concept_id"]: p for p in state.get("priorities") or []}
    notes = state.get("notes") or {}
    by_id = {c["id"]: c for c in concepts}
    out = []
    for cid in lecture_order(concepts, meta):
        c = by_id[cid]
        p = prios.get(cid) or {"action": "복습만", "exam_pct": 0, "status": "진단 안 함"}
        detail = detail_level(p["action"], p["exam_pct"], p["status"])
        n = notes.get(cid)
        if n is None and detail == "짧게":
            body = [x for x in c.get("pages", []) if x not in set(meta)]
            n = short_note(c, body or c.get("pages", []))
        out.append((c, detail, n))
    return out


def notes_html(state: dict, today: date | None = None) -> str:
    """② 시험 대비 요약 노트."""
    today = today or kst_today()
    parts = [_head(state, "빈틈노트 시험 대비 요약 노트", today)]
    rows = note_rows(state)
    if not rows:
        parts.append("<p>요약 노트 없음</p>")
    else:
        cnt = {d: sum(1 for _, x, _ in rows if x == d) for d in ("자세히", "보통", "짧게")}
        parts.append(_stats(list(cnt.items())))
        prios = {p["concept_id"]: p for p in state.get("priorities") or []}
        utts = state.get("utterances") or []
        for i, (c, detail, n) in enumerate(rows, 1):
            p = prios.get(c["id"], {})
            head = (f"<h3>{i}. {esc(c['name'])} {badge(detail, 'blue')}</h3><div>"
                    f"{status_badge(p.get('status', '진단 안 함'))}{badge('출제 점수 ' + str(p.get('exam_pct', 0)))}"
                    f"{action_badge(p['action']) if p.get('action') else ''}</div>")
            quotes = professor_quotes(utts, c["id"], 3)
            parts.append(f"<div class='bt-card'>{head}{note_html(n, quotes)}</div>")
    parts.append(f"<div class='foot'>{esc(FOOTER)}</div>")
    return _doc("빈틈노트 시험 대비 요약 노트", "".join(parts))


def file_names(today: date | None = None) -> tuple[str, str]:
    d = (today or kst_today()).isoformat()
    return f"빈틈노트_공부순서_오답노트_{d}.html", f"빈틈노트_요약노트_{d}.html"


__all__ = ["study_html", "notes_html", "note_rows", "file_names", "MCQ"]
