"""S03 내 취약점 진단: 문제 카드, 예시 답 채우기, 모두 답해야 채점, 채점 결과, 공부 순서 보기."""
from __future__ import annotations

import time

import streamlit as st

import config
from core import llm
from core.diagnose import ESSAY, MCQ, example_answers, grade_blank, grade_essay, grade_mcq, is_answered
from core.figure import figure_html
from core.html import badge, choice_label, esc, question_review_html, status_badge
from core.priority import auto_explain_ids, compute_priorities
from screens.common import (S, add_usage, ai_budget_ok, answer_info, concept_map, error_of, evidence, html,
                            run_parallel, score_map, score_rows, stat_row, step_bar)
from screens import s02

CONF_PLACEHOLDER = "②와 ③ 중에 고민했어요. 두 방법이 어떻게 다른지 모르겠어요."


def order() -> list[str]:
    return [cid for cid in S["diag_ids"] if cid in S["questions"]]


def all_graded() -> bool:
    ids = order()
    return bool(ids) and all(cid in S["grading"] for cid in ids)


def fill_examples() -> None:
    """예시 답을 입력칸의 세션 키와 세션 딕셔너리에 넣는다(입력칸이 그려지기 전에)."""
    ex = example_answers(S["questions"], order())
    for cid, a in ex.items():
        if "mcq_choice" in a:
            S["mcq_" + cid] = a["mcq_choice"]
            S["guess_" + cid] = a["guessed"]
            S["conf_" + cid] = a["confusion"]
            S["mcq_choice"][cid] = a["mcq_choice"]
            S["guessed"][cid] = a["guessed"]
            S["confusion"][cid] = a["confusion"]
        else:
            S["ans_" + cid] = a["answer"]
            S["dk_" + cid] = a["dont_know"]
            S["answers"][cid] = a["answer"]
            S["dont_know"][cid] = a["dont_know"]
    S["show_missing"] = False


def grade(ids: list[str]) -> None:
    """객관식·'모르겠어요'는 코드, 서술형 답은 AI(동시). 실패한 문제는 grade_failed에."""
    cmap = concept_map()
    tasks = []
    for cid in ids:
        q = S["questions"][cid]
        a = answer_info(cid)
        if q["kind"] == MCQ:
            g = grade_mcq(q, a["mcq_choice"], a["guessed"])
            S["grading"][cid] = g
        elif a["dont_know"]:
            S["grading"][cid] = grade_blank(q, "dont_know")
        elif not a["answer"].strip():
            S["grading"][cid] = grade_blank(q, "empty")
        else:
            allowed, ptext = evidence(cid)
            name = cmap[cid]["name"]

            def job(q=q, ans=a["answer"], ptext=ptext, allowed=allowed, name=name):
                u = llm.Usage()
                return grade_essay(name, q, ans, False, ptext, allowed, usage=u), u

            tasks.append((cid, job))
    if tasks and not ai_budget_ok():
        S["grade_failed"] = [cid for cid, _ in tasks]
        return
    t0 = time.time()
    ok, fail = run_parallel(tasks, "서술형 채점 중", config.MAX_WORKERS, "보통 10~30초")
    total = llm.Usage()
    for cid, (g, u) in ok.items():
        S["grading"][cid] = g
        total.merge(u)
    if tasks:
        total.add_stage("③ 채점", time.time() - t0)
    add_usage(total)
    S["grade_failed"] = list(fail.keys())
    if fail:
        e = next(iter(fail.values()))
        code, msg = error_of(e)
        S["grade_error"] = {"code": code, "message": msg, "detail": f"{type(e).__name__}: {e}"}
    else:
        S["grade_error"] = None


def go_priorities() -> None:
    """우선순위를 계산하고 자동 보완 설명을 이 화면에서 다 만든 뒤 ④로 넘어간다."""
    from screens import s04
    grading = {cid: g for cid, g in S["grading"].items() if cid not in S["grade_failed"]}
    S["priorities"] = compute_priorities(score_rows(), grading)
    conf = {cid: (S["confusion"].get(cid) if S["guessed"].get(cid) else "") for cid in S["questions"]}
    ids = [cid for cid in auto_explain_ids(S["priorities"], conf, config.AUTO_EXPLAIN_TOP)
           if cid not in S["explanations"]]
    s04.make_explanations(ids)
    S["step"] = 4
    st.rerun()


def render_inputs(cid: str, q: dict, locked: bool) -> None:
    if q["kind"] == MCQ:
        opts = [0, 1, 2, 3, -1]
        fmt = lambda i: "모르겠어요" if i == -1 else f"{choice_label(i)} {q['choices'][i]}"  # noqa: E731
        k = "mcq_" + cid
        if k in S:
            choice = st.radio("보기", opts, format_func=fmt, key=k, disabled=locked, label_visibility="collapsed")
        else:
            prev = S["mcq_choice"].get(cid)
            choice = st.radio("보기", opts, format_func=fmt, key=k, disabled=locked, label_visibility="collapsed",
                              index=opts.index(prev) if prev in opts else None)
        S["mcq_choice"][cid] = choice
        if choice is not None and choice >= 0:
            gk = "guess_" + cid
            if gk in S:
                guessed = st.checkbox("확신 없이 골랐어요 (찍었어요)", key=gk, disabled=locked)
            else:
                guessed = st.checkbox("확신 없이 골랐어요 (찍었어요)", key=gk, disabled=locked,
                                      value=bool(S["guessed"].get(cid)))
            S["guessed"][cid] = guessed
            if guessed:
                ck = "conf_" + cid
                kw = {} if ck in S else {"value": S["confusion"].get(cid, "")}
                conf = st.text_area("어떤 점이 헷갈렸나요? (선택)", key=ck, disabled=locked,
                                    max_chars=config.CONFUSION_MAX_CHARS, placeholder=CONF_PLACEHOLDER, height=80,
                                    **kw)
                S["confusion"][cid] = conf
        else:
            S["guessed"][cid] = False
    else:
        k = "ans_" + cid
        kw = {} if k in S else {"value": S["answers"].get(cid, "")}
        ans = st.text_area("내 답", key=k, disabled=locked, height=110,
                           placeholder="아는 만큼 2~3문장으로 적어 주세요.", **kw)
        S["answers"][cid] = ans
        dk = "dk_" + cid
        kw2 = {} if dk in S else {"value": bool(S["dont_know"].get(cid))}
        S["dont_know"][cid] = st.checkbox("모르겠어요", key=dk, disabled=locked, **kw2)


def render_card(i: int, cid: str, locked: bool) -> None:
    q = S["questions"][cid]
    pct = score_map()[cid]["pct"]
    name = concept_map()[cid]["name"]
    with st.container(border=True):
        html(f"<div><b>Q{i}. {esc(name)}</b> {badge(q['kind'], 'blue')}{badge('출제 점수 ' + str(pct))}</div>"
             f"<div class='bt-q'>{esc(q['question'])}</div>{figure_html(q.get('figure'))}")
        g = S["grading"].get(cid)
        if g is None:
            render_inputs(cid, q, locked)
            if cid in S["grade_failed"]:
                html('<div class="bt-red">이 문제를 채점하지 못했어요. 답은 그대로 남아 있어요.</div>')
            elif S["show_missing"] and not is_answered(q, **_answer_kwargs(cid)):
                html('<div class="bt-red">아직 답하지 않았어요. 모르면 \'모르겠어요\'를 골라 주세요.</div>')
        else:
            html(question_review_html(q, g, answer_info(cid)).replace(f"<div class=\"bt-q\">{esc(q['question'])}</div>", "", 1))


def _answer_kwargs(cid: str) -> dict:
    a = answer_info(cid)
    return {"answer": a["answer"], "dont_know": a["dont_know"], "mcq_choice": a["mcq_choice"]}


def render() -> None:
    step_bar(3)
    st.title("③ 내 취약점 진단")
    if not S["diag_ids"]:
        st.info("진단할 개념이 없어요. 공부 순서로 바로 갈 수 있어요.")
        if st.button("공부 순서 보기", type="primary", key="bt_to4_empty"):
            go_priorities()
        return
    s02.sync_questions()
    ids = order()
    cmap = concept_map()
    if S["q_failed"]:
        names = [cmap[k.split("|")[0]]["name"] for k in S["q_failed"] if k.split("|")[0] in cmap]
        err = S["q_error"] or {}
        st.error(f"문제를 만들지 못한 개념이 있어 진단에서 뺐어요: {', '.join(names)}. "
                 f"{err.get('message', '')} ({err.get('code', 'E-08')})")
        if err.get("detail"):
            with st.expander("자세한 오류"):
                st.code(err["detail"][:2000])
        if not S["grading"] and st.button("못 만든 문제 다시 만들기", key="bt_remake"):
            s02.make_questions(S["diag_ids"])
            s02.sync_questions()
            st.rerun()
    if not ids:
        return
    graded = all_graded()
    locked = bool(S["grading"])
    infos = {cid: answer_info(cid) for cid in ids}
    n_ans = sum(1 for cid in ids if is_answered(S["questions"][cid], **_answer_kwargs(cid)))
    n_mcq = sum(1 for cid in ids if S["questions"][cid]["kind"] == MCQ)
    st.progress(n_ans / len(ids), text=f"답한 문제 {n_ans} / {len(ids)} · 객관식 {n_mcq} · 서술형 {len(ids) - n_mcq}")
    if S["from_sample"] and not locked and n_ans < len(ids):
        st.caption("샘플로 둘러보는 중이라면 '예시 답 채우기'로 바로 채점까지 가 볼 수 있어요.")
        if st.button("예시 답 채우기 (샘플 체험용)", key="bt_example"):
            fill_examples()
            st.rerun()
    if graded or (S["grading"] and S["grade_failed"]):
        done = [g for cid, g in S["grading"].items() if cid in ids]
        stat_row([(s, sum(1 for g in done if g["status"] == s)) for s in ("앎", "헷갈림", "모름")])
    if S["grade_failed"]:
        err = S["grade_error"] or {}
        st.error(f"서술형 {len(S['grade_failed'])}문제를 채점하지 못했어요. {err.get('message', '')} "
                 f"({err.get('code', 'E-08')})")
        if err.get("detail"):
            with st.expander("자세한 오류"):
                st.code(err["detail"][:2000])

    for i, cid in enumerate(ids, 1):
        render_card(i, cid, locked)
    del infos

    if not S["grading"]:
        st.caption("모든 문제에 답해야 채점해요. 모르면 '모르겠어요'를 고르면 돼요.")
        if st.button("채점하기", type="primary", key="bt_grade", width="stretch"):
            missing = [i for i, cid in enumerate(ids, 1)
                       if not is_answered(S["questions"][cid], **_answer_kwargs(cid))]
            if missing:
                S["show_missing"] = True  # 카드가 버튼보다 먼저 그려지므로 다시 그려 카드 아래 글씨도 보이게
                st.rerun()
            S["show_missing"] = False
            grade(ids)
            st.rerun()
        if S["show_missing"]:
            miss = [f"Q{i}" for i, cid in enumerate(ids, 1)
                    if not is_answered(S["questions"][cid], **_answer_kwargs(cid))]
            if miss:
                st.error(f"아직 답하지 않은 문제: {', '.join(miss)} (E-11)")
        return
    if S["grade_failed"]:
        c1, c2 = st.columns(2)
        if c1.button("채점 못한 문제 다시 채점", type="primary", key="bt_regrade", width="stretch"):
            grade(list(S["grade_failed"]))
            st.rerun()
        if c2.button("채점 못한 문제는 빼고 공부 순서 보기", key="bt_skip_failed", width="stretch"):
            go_priorities()
        return
    if st.button("공부 순서 보기", type="primary", key="bt_to4", width="stretch"):
        go_priorities()
    if S["priorities"] is not None:
        st.caption("이미 만든 공부 순서는 사이드바 ④에서 볼 수 있어요.")
