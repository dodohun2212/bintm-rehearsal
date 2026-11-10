"""S02 출제 포인트 레이더: 순위 목록, 근거, 점수 내역, 문제 형식·빠른 진단, 진단하기."""
from __future__ import annotations

import streamlit as st

import config
from core import diagnose, score
from screens import common as C

EXPLAIN_SCORE = ("출제 가능성 점수는 자료와 녹음의 신호를 정해진 규칙(가중치 v0)으로 더해, 가장 높은 개념을 100점으로 맞춘 "
                 "비교용 점수예요. 확률이 아니며 실제 출제를 보장하지 않습니다.")
TYPE_NAMES = score.TYPE_LABELS


def current_quick() -> bool:
    """빠른 진단 토글의 지금 값(위젯이 그려지기 전이면 세션 값)."""
    return bool(st.session_state.get("w_quick", st.session_state["quick_diag"]))


def current_targets() -> list[str]:
    top = config.QUICK_DIAG_TOP if current_quick() else None
    return diagnose.diag_targets(st.session_state["scores"], top=top)


def _rows_html(rows: list[dict], dim: bool) -> str:
    out = []
    for s in rows:
        badges = "".join(C.badge(label, "b-minus" if minus else "") for label, minus in score.badges(s))
        out.append(
            f'<div class="bt-row{" dim" if dim else ""}"><b>{s["rank"]}</b><span class="nm">{C.esc(s["name"])}</span>'
            f'<span class="bt-bar"><i style="width:{s["pct"]}%"></i></span><b>{s["pct"]}점</b>'
            f'<div style="flex-basis:100%">{badges}</div></div>')
    return "".join(out)


def _detail(scores: list[dict]) -> None:
    concepts = {c["id"]: c for c in st.session_state["concepts"]}
    utts = st.session_state["utterances"]
    with st.expander("점수 내역과 교수님이 한 말 자세히 보기"):
        for s in scores:
            c = concepts[s["concept_id"]]
            lines = [f"<h4>{s['rank']}. {C.esc(c['name'])} · {s['pct']}점 (원점수 {s['raw']:.1f})</h4>",
                     f"<p>{C.esc(c.get('summary'))}</p>", f"<div>등장 페이지 {C.page_badges(c.get('pages'))}</div>"]
            if s["reasons"]:
                lines.append("<ul>" + "".join(
                    f"<li>{C.esc(r['label'])}: {r['points']:+.1f}</li>" for r in s["reasons"]) + "</ul>")
            said = [u for u in utts if u.get("concept_id") == c["id"]]
            if said:
                lines.append("<div><b>교수님이 한 말</b></div><ul>" + "".join(
                    f"<li>“{C.esc(u['quote'])}” {C.badge(TYPE_NAMES.get(u['type'], u['type']), 'b-blue')}"
                    f"<span class='rec'>녹음</span></li>" for u in said) + "</ul>")
            if c.get("objective_quote"):
                lines.append(f"<div>학습목표: “{C.esc(c['objective_quote'])}”</div>")
            C.html_block("".join(lines))
        outside = [u for u in utts if not u.get("concept_id")]
        if outside:
            C.html_block("<h4>개념 목록 밖 언급</h4><ul>" + "".join(
                f"<li>{C.esc(u.get('concept_name'))}: “{C.esc(u['quote'])}” "
                f"{C.badge(TYPE_NAMES.get(u['type'], u['type']), 'b-blue')}</li>" for u in outside) + "</ul>")


def render() -> None:
    C.header(2, "출제 포인트 레이더", "자료와 녹음의 신호로 출제 가능성이 높은 개념부터 보여 줘요.")
    for note in st.session_state["notices"]:
        st.warning(note)
    scores = st.session_state["scores"]
    utts = st.session_state["utterances"]
    graded = bool(st.session_state["grading"])
    all_targets = diagnose.diag_targets(scores)
    n_emph = len({u["quote"] for u in utts if u.get("concept_id")})
    stats_slot = st.empty()
    st.info(C.DISCLAIMER)
    if not st.session_state["transcript"]:
        st.caption("녹음 없이 자료만으로 계산했어요. 녹음을 넣으면 순위가 더 정확해져요.")

    high = [s for s in scores if s["pct"] >= config.DIAG_MIN_PCT]
    low = [s for s in scores if s["pct"] < config.DIAG_MIN_PCT]
    body = _rows_html(high, False)
    if low:
        body += (f'<div style="margin-top:10px;font-size:14px;opacity:.8">아래 {len(low)}개는 출제 가능성 점수가 '
                 f"{config.DIAG_MIN_PCT}점 미만이라 진단하지 않고 '복습만'으로 둬요</div>" + _rows_html(low, True))
    C.html_block(body)
    st.caption(EXPLAIN_SCORE)
    _detail(scores)

    st.markdown("#### 진단 문제 고르기")
    if "w_q_mode" not in st.session_state:
        st.session_state["w_q_mode"] = st.session_state["q_mode"]
    st.radio("문제 형식", diagnose.MODES, key="w_q_mode", horizontal=True, disabled=graded,
             help=f"섞어서: 출제 점수 {config.ESSAY_MIN_PCT}점 이상은 서술형, 나머지는 객관식")
    st.session_state["q_mode"] = st.session_state["w_q_mode"]
    if len(all_targets) > config.QUICK_DIAG_TOP:
        if "w_quick" not in st.session_state:
            st.session_state["w_quick"] = st.session_state["quick_diag"]
        rest = len(all_targets) - config.QUICK_DIAG_TOP
        st.toggle(f"빠른 진단: 출제 가능성 상위 {config.QUICK_DIAG_TOP}개만 풀기", key="w_quick", disabled=graded,
                  help=f"{len(all_targets)}문제 대신 {config.QUICK_DIAG_TOP}문제만 풀어요. 나머지 {rest}개는 "
                       "'진단 안 함'(이해도 0.5)으로 공부 순서에 들어가요.")
        st.session_state["quick_diag"] = st.session_state["w_quick"]
    targets = current_targets()
    stats_slot.html('<div class="bt">' + _stats_html(len(scores), n_emph, len(targets)) + "</div>")
    if st.button(f"{len(targets)}개 개념 진단하기", type="primary", disabled=not targets):
        if not graded:
            st.session_state["diag_ids"] = targets
        st.session_state["step"] = 3
        st.rerun()
    if not targets:
        st.caption(f"출제 가능성 점수 {config.DIAG_MIN_PCT}점 이상인 개념이 없어 진단할 문제가 없어요.")


def _stats_html(n_concepts: int, n_emph: int, n_targets: int) -> str:
    items = [("찾은 개념", n_concepts), ("교수님 강조", n_emph), ("진단할 개념", n_targets)]
    cells = "".join(f'<div class="bt-stat"><span>{k}</span><b>{v}</b></div>' for k, v in items)
    return f'<div class="bt-stats">{cells}</div>'
