"""S02 출제 포인트 레이더: 순위 + 근거 + 문제 형식·빠른 진단 + 문제 만들기(버튼 아래 진행 막대)."""
from __future__ import annotations

import time

import streamlit as st

import config
from core import llm
from core.diagnose import MODES, diag_targets, make_question, other_concepts_text, question_kind
from core.html import DISCLAIMER, PCT_NOTE, badge, bar, esc, signal_badges
from core.score import TYPE_LABELS
from core.utterances import emphasis_count
from screens.common import (S, add_usage, ai_budget_ok, concept_map, error_of, evidence, html, run_parallel,
                            sample_cache, score_map, score_rows, stat_row, step_bar)


def current_targets() -> list[str]:
    quick = S.get("bt_quick", S["quick_diag"])
    return diag_targets(score_rows(), top=config.QUICK_DIAG_TOP if quick else None)


def kind_for(cid: str, mode: str | None = None) -> str:
    return question_kind(score_map()[cid]["pct"], mode or S["q_mode"])


def store_key(cid: str, mode: str | None = None) -> str:
    return f"{cid}|{kind_for(cid, mode)}"


def sync_questions() -> None:
    """지금 고른 형식의 문제를 questions에 모은다(문제는 (개념, 형식)으로 보관)."""
    S["questions"] = {cid: S["q_store"][store_key(cid)] for cid in S["diag_ids"] if store_key(cid) in S["q_store"]}


def make_questions(targets: list[str]) -> None:
    """빠진 문제만 만든다. 샘플 자료는 서버 공용 저장소에서 먼저 꺼낸다."""
    cmap = concept_map()
    names = [cmap[c]["name"] for c in targets]
    cache = sample_cache() if S["from_sample"] else None
    tasks, keys = [], {}
    for cid in targets:
        key = store_key(cid)
        if key in S["q_store"]:
            continue
        kind = kind_for(cid)
        others = other_concepts_text(names, cmap[cid]["name"])
        ckey = (S["run_id"], cid, kind, tuple(n for n in names if n != cmap[cid]["name"]))
        if cache is not None:
            hit = cache.get(ckey)
            if hit is not None:
                S["q_store"][key] = hit  # 저장된 문제: AI 호출·사용량 없음
                continue
        allowed, ptext = evidence(cid)  # 스레드를 만들기 전에 꺼낸다
        concept = dict(cmap[cid])

        def job(concept=concept, kind=kind, ptext=ptext, allowed=allowed, others=others):
            u = llm.Usage()
            return make_question(concept, kind, ptext, allowed, others, usage=u), u

        tasks.append((key, job))
        keys[key] = ckey
    if not tasks:
        S["q_failed"] = [k for k in S["q_failed"] if k not in S["q_store"]]
        return
    if not ai_budget_ok():
        return
    t0 = time.time()
    ok, fail = run_parallel(tasks, "문제 만드는 중", config.MAX_WORKERS, "보통 20~40초")
    total = llm.Usage()
    for key, (q, u) in ok.items():
        S["q_store"][key] = q
        total.merge(u)
        if cache is not None:
            cache.put(keys[key], q)
    total.add_stage("② 문제 만들기", time.time() - t0)
    add_usage(total)
    S["q_failed"] = [k for k in fail]
    if fail:
        code, msg = error_of(next(iter(fail.values())))
        S["q_error"] = {"code": code, "message": msg, "detail": str(next(iter(fail.values())))}
    else:
        S["q_error"] = None


def render() -> None:
    step_bar(2)
    st.title("② 출제 포인트 레이더")
    for n in S["notices"]:
        st.warning(n)
    rows = score_rows()
    utts = S["utterances"]
    targets = current_targets()
    stat_row([("찾은 개념", len(rows)), ("교수님 강조", emphasis_count(utts)), ("진단할 개념", len(targets))])
    html(f'<div class="bt-warn">⚠️ {esc(DISCLAIMER)}</div>')
    if not S["transcript"]:
        st.info("녹음 없이 자료만으로 계산했어요. 녹음을 넣으면 순위가 더 정확해져요.")

    below = [r for r in rows if r["pct"] < config.DIAG_MIN_PCT]
    out = []
    for r in rows:
        if below and r is below[0]:
            out.append(f'<p class="bt-muted" style="margin-top:12px">아래 {len(below)}개는 출제 가능성 점수가 '
                       f'{config.DIAG_MIN_PCT}점 미만이라 진단하지 않고 \'복습만\'으로 둬요.</p>')
        dim = "opacity:.55;" if r["pct"] < config.DIAG_MIN_PCT else ""
        out.append(f'<div style="{dim}display:grid;grid-template-columns:2em 1fr 130px;gap:8px;align-items:center;'
                   f'padding:7px 0;border-bottom:1px solid #e5e7eb"><b>{r["rank"]}</b>'
                   f'<div><b>{esc(r["name"])}</b><div>{signal_badges(r["reasons"])}</div></div>'
                   f'<div>{bar(r["pct"])}<b>{r["pct"]}점</b></div></div>')
    html("".join(out))
    st.caption(PCT_NOTE)

    with st.expander("점수 내역과 교수님이 한 말 자세히 보기"):
        cmap = concept_map()
        for r in rows:
            c = cmap[r["concept_id"]]
            parts = [f"<h4 style='margin:10px 0 2px'>{r['rank']}. {esc(r['name'])} · {r['pct']}점 "
                     f"<span class='bt-muted'>(원점수 {r['raw']:.1f})</span></h4>",
                     f"<div>{esc(c.get('summary', ''))}</div>",
                     f"<div class='bt-muted'>등장 페이지: {', '.join('p.' + str(p) for p in c.get('pages', []))}</div>"]
            if c.get("objective_quote"):
                parts.append(f"<div>학습목표: “{esc(c['objective_quote'])}”</div>")
            items = "".join(f"<li>{esc(x['label'].split(':')[0])} {x['points']:+.1f}</li>" for x in r["reasons"])
            parts.append(f"<ul>{items or '<li>신호 없음</li>'}</ul>")
            quotes = [u for u in utts if u.get("concept_id") == r["concept_id"]]
            if quotes:
                parts.append("<ul>" + "".join(f"<li>{badge(TYPE_LABELS.get(u['type'], u['type']))} “{esc(u['quote'])}”"
                                              f" (강도 {u['strength']})</li>" for u in quotes) + "</ul>")
            html("".join(parts))
        outside = [u for u in utts if not u.get("concept_id")]
        if outside:
            html("<h4>개념 목록 밖 언급</h4><ul>" + "".join(
                f"<li>{esc(u['concept_name'])}: “{esc(u['quote'])}” ({esc(TYPE_LABELS.get(u['type'], u['type']))})</li>"
                for u in outside) + "</ul>")

    st.subheader("진단 문제 형식")
    graded = bool(S["grading"])
    if "bt_mode" not in S:
        mode = st.radio("문제 형식", MODES, index=MODES.index(S["q_mode"]), horizontal=True, key="bt_mode",
                        disabled=graded,
                        help=f"섞어서: 출제 점수 {config.ESSAY_MIN_PCT}점 이상은 서술형, 나머지는 객관식")
    else:
        mode = st.radio("문제 형식", MODES, horizontal=True, key="bt_mode", disabled=graded,
                        help=f"섞어서: 출제 점수 {config.ESSAY_MIN_PCT}점 이상은 서술형, 나머지는 객관식")
    S["q_mode"] = mode
    all_targets = diag_targets(rows)
    if len(all_targets) > config.QUICK_DIAG_TOP:
        m = len(all_targets) - config.QUICK_DIAG_TOP
        help_txt = (f"{len(all_targets)}문제 대신 {config.QUICK_DIAG_TOP}문제만 풀어요. 나머지 {m}개는 '진단 안 함'"
                    f"(이해도 0.5)으로 공부 순서를 계산해요.")
        if "bt_quick" not in S:
            q = st.toggle(f"빠른 진단: 출제 가능성 상위 {config.QUICK_DIAG_TOP}개만 풀기", value=S["quick_diag"],
                          key="bt_quick", disabled=graded, help=help_txt)
        else:
            q = st.toggle(f"빠른 진단: 출제 가능성 상위 {config.QUICK_DIAG_TOP}개만 풀기", key="bt_quick",
                          disabled=graded, help=help_txt)
        S["quick_diag"] = q
    else:
        S["quick_diag"] = False
    targets = current_targets()
    if graded:
        st.caption("채점한 뒤에는 문제 형식과 빠른 진단을 바꿀 수 없어요.")
    n = len(targets)
    if n == 0:
        st.info(f"출제 가능성 점수 {config.DIAG_MIN_PCT}점 이상인 개념이 없어 진단할 문제가 없어요.")
        if st.button("공부 순서 바로 보기", key="bt_to4_nodiag"):
            S["diag_ids"] = []
            S["step"] = 3
            st.rerun()
        return
    label = f"{n}개 개념 진단하기" if not graded else "③ 진단 결과 보기"
    if st.button(label, type="primary", key="bt_diag", width="stretch"):
        if not graded:
            S["diag_ids"] = targets
            make_questions(targets)
            sync_questions()
            if not S["questions"] and S["q_failed"]:
                err = S["q_error"] or {}
                st.error(f"문제를 하나도 만들지 못했어요. {err.get('message', '')} ({err.get('code', 'E-08')})")
                return
        S["step"] = 3
        st.rerun()
