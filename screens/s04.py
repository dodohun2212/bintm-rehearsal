"""S04 우선순위 보완 학습: 공부 순서와 오답노트 / 시험 대비 요약 노트(고른 보기만 그림), 내려받기 2개."""
from __future__ import annotations

import hashlib
import time

import streamlit as st

import config
from core import llm
from core.explain import make_explanation
from core.export import file_names, note_rows, notes_html, study_html
from core.figure import figure_html
from core.html import (action_badge, badge, bar, esc, explanation_html, note_html, question_review_html,
                       status_badge)
from core.note import make_note
from core.pageimg import render_page
from core.utterances import professor_quotes
from screens.common import (S, add_usage, ai_budget_ok, answer_info, concept_map, error_of, evidence,
                            export_state, html, reset_state, run_parallel, sample_cache, stat_row, step_bar)

VIEWS = ("🎯 공부 순서와 오답노트", "📒 시험 대비 요약 노트")
GROUP_TEXT = {"지금 당장": "여기부터 보세요. 출제 가능성이 높은데 아직 모르는 개념이에요.",
              "다음": "그다음에 볼 개념이에요.",
              "복습만": "알고 있거나 출제 가능성이 낮은 개념이에요."}


@st.cache_data(show_spinner=False, max_entries=200)
def page_jpeg(run_id: str, n: int, _data: bytes) -> bytes | None:
    """원본 페이지 그림(PDF만). PDF 바이트는 해시하지 않는다."""
    return render_page(_data, n, 900)


def _ans_hash(cid: str) -> str:
    a = answer_info(cid)
    raw = f"{a['answer']}|{a['dont_know']}|{a['mcq_choice']}|{a['guessed']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _status(cid: str) -> str:
    p = next((p for p in S["priorities"] or [] if p["concept_id"] == cid), None)
    return p["status"] if p else "진단 안 함"


def make_explanations(ids: list[str]) -> None:
    """보완 설명을 동시에 만든다. 샘플 자료에서 같은 답이면 저장된 설명을 다시 쓴다."""
    cmap = concept_map()
    cache = sample_cache() if S["from_sample"] else None
    tasks, keys = [], {}
    for cid in ids:
        status = _status(cid)
        q = S["questions"].get(cid)
        g = S["grading"].get(cid) if cid not in S["grade_failed"] else None
        a = answer_info(cid)
        conf = a["confusion"] if a["guessed"] else ""
        ckey = ("explain", S["run_id"], cid, status, _ans_hash(cid), conf)
        if cache is not None:
            hit = cache.get(ckey)
            if hit is not None:
                S["explanations"][cid] = hit
                continue
        allowed, ptext = evidence(cid)
        concept = dict(cmap[cid])

        def job(concept=concept, status=status, q=q, g=g, a=a, conf=conf, ptext=ptext, allowed=allowed):
            u = llm.Usage()
            return make_explanation(concept, status, q, g, a, conf, ptext, allowed, usage=u), u

        tasks.append((cid, job))
        keys[cid] = ckey
    S["explain_failed"] = [c for c in S["explain_failed"] if c not in ids]
    if not tasks or not ai_budget_ok():
        return
    t0 = time.time()
    ok, fail = run_parallel(tasks, "보완 설명 만드는 중", config.MAX_WORKERS_S04, "보통 20~40초")
    total = llm.Usage()
    for cid, (ex, u) in ok.items():
        S["explanations"][cid] = ex
        total.merge(u)
        if cache is not None:
            cache.put(keys[cid], ex)
    total.add_stage("④ 보완 설명", time.time() - t0)
    add_usage(total)
    S["explain_failed"] = S["explain_failed"] + list(fail.keys())
    if fail:
        e = next(iter(fail.values()))
        code, msg = error_of(e)
        S["explain_error"] = {"code": code, "message": msg, "detail": f"{type(e).__name__}: {e}"}


def note_targets() -> list[tuple[str, str]]:
    """AI로 만들 요약 노트: '자세히'·'보통' 중 아직 없는 것."""
    return [(c["id"], d) for c, d, n in note_rows(export_state()) if d in ("자세히", "보통")
            and c["id"] not in S["notes"]]


def make_notes(targets: list[tuple[str, str]]) -> None:
    cmap = concept_map()
    cache = sample_cache() if S["from_sample"] else None
    prios = {p["concept_id"]: p for p in S["priorities"] or []}
    utts = list(S["utterances"])  # 스레드에 넘길 값은 미리 꺼낸다
    tasks, keys = [], {}
    for cid, detail in targets:
        g = S["grading"].get(cid) if cid not in S["grade_failed"] else None
        a = answer_info(cid)
        ckey = ("note", S["run_id"], cid, detail, _status(cid), _ans_hash(cid), a["confusion"] if a["guessed"] else "")
        if cache is not None:
            hit = cache.get(ckey)
            if hit is not None:
                S["notes"][cid] = hit
                continue
        allowed, ptext = evidence(cid)
        concept, prio = dict(cmap[cid]), dict(prios.get(cid) or {})

        def job(concept=concept, detail=detail, prio=prio, g=g, ptext=ptext, allowed=allowed):
            u = llm.Usage()
            return make_note(concept, detail, prio, g, utts, ptext, allowed, usage=u), u

        tasks.append((cid, job))
        keys[cid] = ckey
    ids = [c for c, _ in targets]
    S["notes_failed"] = [c for c in S["notes_failed"] if c not in ids]
    if not tasks or not ai_budget_ok():
        return
    t0 = time.time()
    ok, fail = run_parallel(tasks, "요약 노트 만드는 중", config.MAX_WORKERS_S04, "보통 20~40초")
    total = llm.Usage()
    for cid, (n, u) in ok.items():
        S["notes"][cid] = n
        total.merge(u)
        if cache is not None:
            cache.put(keys[cid], n)
    total.add_stage("④ 요약 노트", time.time() - t0)
    add_usage(total)
    S["notes_failed"] = S["notes_failed"] + list(fail.keys())
    if fail:
        e = next(iter(fail.values()))
        code, msg = error_of(e)
        S["notes_error"] = {"code": code, "message": msg, "detail": f"{type(e).__name__}: {e}"}


def page_images(cid: str, pages: list[int]) -> None:
    if not S["material_bytes"] or not pages:
        return
    show = pages[:2]
    with st.expander("강의자료 원본 보기 · " + ", ".join(f"p.{p}" for p in show)):
        for p in show:
            img = page_jpeg(S["run_id"], p, S["material_bytes"])
            if img:
                st.image(img, caption=f"p.{p}", width="stretch")


def concept_card(p: dict) -> None:
    cid = p["concept_id"]
    q = S["questions"].get(cid)
    g = S["grading"].get(cid)
    ex = S["explanations"].get(cid)
    with st.container(border=True):
        html(f"<div><b>{p['rank']}. {esc(p['name'])}</b></div><div>{status_badge(p['status'])}"
             f"{badge('출제 점수 ' + str(p['exam_pct']))}{badge('우선순위 ' + str(p['priority']))}</div>")
        if q:
            score = f" · {g['status']} {g['score']}/10" if g else ""
            with st.expander("📝 내 문제와 답 다시 보기" + score):
                html(question_review_html(q, g, answer_info(cid), figure_html(q.get("figure"))))
        if ex:
            html(explanation_html(ex))
            page_images(cid, ex.get("check_pages") or ex.get("source_pages") or [])
        elif cid in S["explain_failed"]:
            err = S["explain_error"] or {}
            html(f'<div class="bt-red">설명을 만들지 못했어요. {esc(err.get("message", ""))} '
                 f'({esc(err.get("code", "E-08"))})</div>')
            if st.button("설명 다시 만들기", key=f"bt_reexp_{cid}"):
                make_explanations([cid])
                st.rerun()
        else:
            if st.button("설명 보기", key=f"bt_exp_{cid}"):
                make_explanations([cid])
                st.rerun()


def downloads(where: str) -> None:
    st_ = export_state()
    f1, f2 = file_names()
    c1, c2 = st.columns(2)
    c1.download_button("📥 공부 순서·오답노트 내려받기", study_html(st_).encode("utf-8"), file_name=f1,
                       mime="text/html", key=f"bt_dl1_{where}", width="stretch")
    notes_ready = bool(S["notes_started"]) or not note_targets()
    c2.download_button("📒 요약 노트 내려받기", notes_html(st_).encode("utf-8") if notes_ready else b"",
                       file_name=f2, mime="text/html", key=f"bt_dl2_{where}", width="stretch",
                       disabled=not notes_ready,
                       help=None if notes_ready else "'📒 시험 대비 요약 노트'를 열면 만들어져요.")


def render_study() -> None:
    prios = S["priorities"]
    groups = {a: [p for p in prios if p["action"] == a] for a in ("지금 당장", "다음", "복습만")}
    for act in ("지금 당장", "다음"):
        items = groups[act]
        if not items:
            continue
        html(f"<h3>{action_badge(act)} {len(items)}개</h3><p class='bt-muted'>{esc(GROUP_TEXT[act])}</p>")
        if act == "다음":
            todo = [p["concept_id"] for p in items if p["concept_id"] not in S["explanations"]]
            if todo and st.button(f"'다음' 개념 설명 {len(todo)}개 한 번에 보기", key="bt_next_all"):
                make_explanations(todo)
                st.rerun()
        for p in items:
            concept_card(p)
    review = groups["복습만"]
    if review:
        html(f"<h3>{action_badge('복습만')} {len(review)}개</h3><p class='bt-muted'>{esc(GROUP_TEXT['복습만'])}</p>")
        conf_ids = {cid for cid in S["questions"] if S["guessed"].get(cid) and (S["confusion"].get(cid) or "").strip()}
        for p in review:
            if p["concept_id"] in conf_ids:
                concept_card(p)  # 헷갈린 점을 적은 개념은 접지 않는다
        rest = [p for p in review if p["concept_id"] not in conf_ids]
        if rest:
            with st.expander(f"복습만 {len(rest)}개 펼치기"):
                st.caption("'진단 안 함'은 출제 가능성 점수가 20점 미만이라 문제를 내지 않은 개념이에요.")
                for p in rest:
                    concept_card(p)
    with st.expander("전체 표로 보기"):
        rows = "".join(f"<tr><td>{p['rank']}</td><td>{esc(p['name'])}</td><td>{bar(p['exam_pct'])}{p['exam_pct']}점</td>"
                       f"<td>{status_badge(p['status'])}</td><td>{bar(p['priority'], '#dc2626')}{p['priority']}</td>"
                       f"<td>{action_badge(p['action'])}</td></tr>" for p in prios)
        html(f"<table class='bt-tbl'><tr><th>순위</th><th>개념</th><th>출제 점수</th><th>이해 상태</th>"
             f"<th>우선순위</th><th>권장</th></tr>{rows}</table>"
             "<p class='bt-muted'>우선순위 = 출제 점수 × (1 − 이해도). 이해도: 앎 1.0 · 헷갈림 0.5 · 모름 0 · 진단 안 함 0.5</p>")


def render_notes() -> None:
    targets = note_targets()
    if targets and not S["notes_started"]:
        S["notes_started"] = True
        make_notes(targets)
        st.rerun()
    rows = note_rows(export_state())
    cnt = {d: sum(1 for _, x, _ in rows if x == d) for d in ("자세히", "보통", "짧게")}
    stat_row(list(cnt.items()))
    st.caption("강의 순서대로 모든 개념을 정리했어요. 중요한 개념(지금 당장·출제 점수 50점 이상·진단에서 모름)일수록 자세히 써요.")
    if S["notes_failed"]:
        err = S["notes_error"] or {}
        st.error(f"요약 노트 {len(S['notes_failed'])}개를 만들지 못했어요. {err.get('message', '')} "
                 f"({err.get('code', 'E-08')})")
        if st.button("요약 노트 다시 만들기", key="bt_renote"):
            make_notes([(c, d) for c, d in note_targets() if c in S["notes_failed"]])
            st.rerun()
    prios = {p["concept_id"]: p for p in S["priorities"] or []}
    for i, (c, detail, n) in enumerate(rows, 1):
        p = prios.get(c["id"], {})
        with st.container(border=True):
            html(f"<div><b>{i}. {esc(c['name'])}</b> {badge(detail, 'blue')}</div><div>"
                 f"{status_badge(p.get('status', '진단 안 함'))}{badge('출제 점수 ' + str(p.get('exam_pct', 0)))}"
                 f"{action_badge(p['action']) if p.get('action') else ''}</div>"
                 + note_html(n, professor_quotes(S["utterances"], c["id"], 3)))
            if n:
                page_images(c["id"], n.get("source_pages") or [])


def render() -> None:
    step_bar(4)
    st.title("④ 우선순위 보완 학습")
    prios = S["priorities"]
    if prios is None:
        st.info("③에서 채점한 뒤 '공부 순서 보기'를 눌러 주세요.")
        return
    groups = [sum(1 for p in prios if p["action"] == a) for a in ("지금 당장", "다음", "복습만")]
    stat_row(list(zip(("지금 당장", "다음", "복습만"), groups)))
    downloads("top")
    if hasattr(st, "segmented_control"):
        view = st.segmented_control("보기", VIEWS, key="bt_view", default=S["view"], label_visibility="collapsed")
    else:  # pragma: no cover
        view = st.radio("보기", VIEWS, key="bt_view", horizontal=True, index=VIEWS.index(S["view"]))
    view = view or S["view"]
    S["view"] = view
    if view == VIEWS[0]:
        render_study()
    else:
        render_notes()
    st.divider()
    downloads("bottom")
    if st.button("🔄 다른 자료로 다시", key="bt_reset"):
        reset_state()
        st.rerun()
