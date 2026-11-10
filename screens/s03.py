"""S03 내 취약점 진단: 문제 만들기(동시), 답 입력, 예시 답 채우기, 채점(객관식 코드·서술형 AI)."""
from __future__ import annotations

import streamlit as st

import config
from core import diagnose
from core.diagnose import DONT_KNOW, ESSAY, MCQ
from core.figure import figure_html
from screens import common as C

CHOICE_MARKS = "①②③④"
MISSING_TEXT = "아직 답하지 않았어요. 모르면 '모르겠어요'를 골라 주세요."


def _concepts() -> dict:
    return {c["id"]: c for c in st.session_state["concepts"]}


def _pct() -> dict:
    return {s["concept_id"]: s["pct"] for s in st.session_state["scores"]}


def wanted_kinds() -> dict[str, str]:
    mode = st.session_state["q_mode"]
    pct = _pct()
    return {cid: diagnose.choose_kind(pct[cid], mode) for cid in st.session_state["diag_ids"]}


def ensure_questions() -> None:
    """(개념, 고른 형식)마다 문제를 만든다. 샘플 자료면 서버 공용 저장소에서 꺼내 다시 쓴다."""
    kinds = wanted_kinds()
    store, fails = st.session_state["q_store"], st.session_state["q_fail_store"]
    concepts = _concepts()
    names = [concepts[cid]["name"] for cid in st.session_state["diag_ids"]]
    cache = C.sample_cache() if st.session_state["from_sample"] else None
    todo = {}
    for cid, kind in kinds.items():
        key = f"{cid}|{kind}"
        if key in store or key in fails:
            continue
        cache_key = (st.session_state["run_id"], cid, kind, tuple(names))
        if cache is not None:
            hit = cache.get(cache_key)
            if hit is not None:  # 저장된 문제: AI를 부르지 않으므로 사용량을 더하지 않는다
                store[key] = hit
                continue
        todo[key] = (concepts[cid], kind, cache_key)
    if todo:
        if C.ai_blocked():
            C.show_error("E-17")
            st.stop()
        material, meta = st.session_state["material"], st.session_state["meta_pages"]

        def work(arg, usage):  # 스레드 안: 세션을 읽지 않는다
            concept, kind, _ = arg
            return diagnose.make_question(concept, kind, material, meta, names, usage)

        with st.spinner("진단 문제를 만들고 있어요…"):
            results, errors, usage, secs = C.run_parallel(work, todo, "문제 만드는 중")
        C.add_usage(usage, "문제 만들기", secs)
        for key, q in results.items():
            store[key] = q
            if cache is not None:
                cache.put(todo[key][2], q)
        for key, exc in errors.items():
            fails[key] = exc
    questions, failed = {}, []
    for cid, kind in kinds.items():
        key = f"{cid}|{kind}"
        if key in store:
            questions[cid] = store[key]
        else:
            failed.append(concepts[cid]["name"])
    st.session_state["questions"] = questions
    st.session_state["q_failed"] = failed
    if failed and not questions:
        msg, code = C.failure_message({k: v for k, v in fails.items()})
        C.show_error(code, C.first_error_text(fails))
        st.stop()


# ---------- 지금 입력값 (위젯 값이 먼저, 없으면 세션 딕셔너리) ----------
def cur_answer(cid: str) -> str:
    return st.session_state.get(f"ans_{cid}", st.session_state["answers"].get(cid, ""))


def cur_dont_know(cid: str) -> bool:
    return bool(st.session_state.get(f"dk_{cid}", st.session_state["dont_know"].get(cid, False)))


def cur_choice(cid: str):
    return st.session_state.get(f"mcq_{cid}", st.session_state["mcq_choice"].get(cid))


def cur_guessed(cid: str) -> bool:
    return bool(st.session_state.get(f"guess_{cid}", st.session_state["guessed"].get(cid, False)))


def answered(q: dict) -> bool:
    cid = q["concept_id"]
    return diagnose.is_answered(q, cur_answer(cid), cur_dont_know(cid), cur_choice(cid))


def fill_examples(questions: list[dict]) -> None:
    """예시 답 채우기: 입력칸이 그려지기 전에 세션 키에 넣고 다시 그린다."""
    for cid, a in diagnose.example_answers(questions).items():
        if "answer" in a:
            st.session_state[f"ans_{cid}"] = a["answer"]
            st.session_state[f"dk_{cid}"] = a["dont_know"]
            st.session_state["answers"][cid] = a["answer"]
            st.session_state["dont_know"][cid] = a["dont_know"]
        else:
            st.session_state[f"mcq_{cid}"] = a["choice"]
            st.session_state[f"guess_{cid}"] = a["guessed"]
            st.session_state[f"conf_{cid}"] = a["confusion"]
            st.session_state["mcq_choice"][cid] = a["choice"]
            st.session_state["guessed"][cid] = a["guessed"]
            st.session_state["confusion"][cid] = a["confusion"]
    st.session_state["show_missing"] = False
    st.session_state["missing_labels"] = []


def _seed(key: str, value) -> None:
    """입력칸 세션 키가 없을 때만 보관해 둔 값을 넣는다(기본값을 두 번 정하지 않게)."""
    if key not in st.session_state:
        st.session_state[key] = value


def _result_html(q: dict, g: dict) -> str:
    cid = q["concept_id"]
    err = f" · {C.esc(g['error_type'])}" if g.get("error_type") else ""
    out = [f'<div>{C.status_badge(g["status"])}<b>{g["score"]}/10</b>{err}</div><div>{C.paragraphs(g.get("reason"))}</div>']
    if q["kind"] == MCQ:
        choice = st.session_state["mcq_choice"].get(cid)
        items = []
        for i, c in enumerate(q["choices"]):
            cls = "bt-right" if i == q["answer_index"] else ("bt-wrong" if i == choice else "")
            mark = " ← 정답" if i == q["answer_index"] else (" ← 내 답" if i == choice else "")
            items.append(f'<div class="bt-choice {cls}">{CHOICE_MARKS[i]} {C.esc(c)}{mark}</div>')
        if choice == DONT_KNOW:
            items.append('<div class="bt-choice bt-wrong">모르겠어요 ← 내 답</div>')
        out.append("".join(items))
        conf = (st.session_state["confusion"].get(cid) or "").strip()
        if conf and st.session_state["guessed"].get(cid):
            out.append(f'<div class="bt-reply">💬 내가 헷갈린 점: {C.esc(conf)}</div>')
        out.append(f"<div><b>해설</b> {C.paragraphs(q.get('explanation'))}</div>")
        out.append(f"<div>근거 {C.page_badges(q.get('source_pages'))}</div>")
    return "".join(out)


def _card(i: int, q: dict, pct: int, graded: dict, failed: list) -> None:
    cid = q["concept_id"]
    g = graded.get(cid)
    locked = g is not None
    with st.container(border=True):
        kind_badge = C.badge(q["kind"], "b-blue")
        C.html_block(f'<div><b>Q{i}. {C.esc(q["name"])}</b> {kind_badge}{C.badge(f"출제 점수 {pct}")}</div>'
                     f'<div class="bt-q">{C.esc(q["question"])}</div>{figure_html(q.get("figure"))}')
        if q["kind"] == ESSAY:
            _seed(f"ans_{cid}", st.session_state["answers"].get(cid, ""))
            _seed(f"dk_{cid}", st.session_state["dont_know"].get(cid, False))
            st.text_area("내 답", key=f"ans_{cid}", placeholder="아는 만큼 2~3문장으로 적어 주세요.", disabled=locked)
            st.checkbox("모르겠어요", key=f"dk_{cid}", disabled=locked)
            st.session_state["answers"][cid] = st.session_state[f"ans_{cid}"]
            st.session_state["dont_know"][cid] = st.session_state[f"dk_{cid}"]
        else:
            options = [0, 1, 2, 3, DONT_KNOW]
            labels = {i2: f"{CHOICE_MARKS[i2]} {c}" for i2, c in enumerate(q["choices"])}
            labels[DONT_KNOW] = "모르겠어요"
            _seed(f"mcq_{cid}", st.session_state["mcq_choice"].get(cid))
            st.radio("보기", options, key=f"mcq_{cid}", format_func=lambda v: labels[v], disabled=locked,
                     label_visibility="collapsed")
            choice = st.session_state[f"mcq_{cid}"]
            st.session_state["mcq_choice"][cid] = choice
            if choice is not None and choice != DONT_KNOW:
                _seed(f"guess_{cid}", st.session_state["guessed"].get(cid, False))
                st.checkbox("확신 없이 골랐어요 (찍었어요)", key=f"guess_{cid}", disabled=locked)
                st.session_state["guessed"][cid] = st.session_state[f"guess_{cid}"]
                if st.session_state[f"guess_{cid}"]:
                    _seed(f"conf_{cid}", st.session_state["confusion"].get(cid, ""))
                    st.text_area("어떤 점이 헷갈렸나요? (선택)", key=f"conf_{cid}", max_chars=config.CONFUSION_MAX_CHARS,
                                 placeholder="②와 ③ 중에 고민했어요. 두 방법이 어떻게 다른지 모르겠어요.", disabled=locked)
                    st.session_state["confusion"][cid] = st.session_state[f"conf_{cid}"]
                else:
                    st.session_state["confusion"][cid] = ""
            else:
                st.session_state["guessed"][cid] = False
                st.session_state["confusion"][cid] = ""
        if st.session_state["show_missing"] and not locked and not answered(q):
            C.html_block(f'<div class="bt-red">{MISSING_TEXT}</div>')
        if cid in failed:
            C.html_block('<div class="bt-red">이 문제를 채점하지 못했어요. 아래 "채점 못한 문제 다시 채점"을 눌러 주세요.</div>')
        if g:
            C.html_block(_result_html(q, g))
            if q["kind"] == ESSAY:
                with st.expander("모범 답안과 루브릭 보기"):
                    rub = g.get("rubric_scores")
                    rows = "".join(
                        f"<li>{C.esc(r['point'])}: {rub[k] if rub else '-'} / {r['score']}</li>"
                        for k, r in enumerate(q["rubric"]))
                    C.html_block(f"<div><b>모범 답안</b> {C.esc(q['answer'])}</div><ul>{rows}</ul>"
                                 f"<div>근거 {C.page_badges(q.get('source_pages'))}</div>")


def grade(questions: list[dict], only: list[str] | None = None) -> None:
    """객관식·'모르겠어요'는 코드, 답이 있는 서술형만 AI(동시). 실패한 문제는 표시하고 그 문제만 다시."""
    grading = st.session_state["grading"]
    material = st.session_state["material"]
    todo = {}
    for q in questions:
        cid = q["concept_id"]
        if only is not None and cid not in only:
            continue
        if q["kind"] == MCQ:
            grading[cid] = diagnose.grade_mcq(q, st.session_state["mcq_choice"].get(cid), st.session_state["guessed"].get(cid, False))
        elif st.session_state["dont_know"].get(cid) or not (st.session_state["answers"].get(cid) or "").strip():
            grading[cid] = diagnose.grade_essay(q, st.session_state["answers"].get(cid, ""), st.session_state["dont_know"].get(cid, False), material)
        else:
            todo[cid] = (q, st.session_state["answers"][cid])
    failed = []
    if todo:
        if C.ai_blocked():
            C.show_error("E-17")
            return

        def work(arg, usage):  # 스레드 안: 세션을 읽지 않는다
            q, answer = arg
            return diagnose.grade_essay(q, answer, False, material, usage)

        with st.spinner("서술형 답을 채점하고 있어요…"):
            results, errors, usage, secs = C.run_parallel(work, todo, "채점 중")
        C.add_usage(usage, "채점", secs)
        grading.update(results)
        failed = list(errors)
        st.session_state["grade_error"] = C.first_error_text(errors)
        st.session_state["grade_fail_codes"] = {k: C.error_code(e) for k, e in errors.items()}
    st.session_state["grade_failed"] = failed


def render() -> None:
    C.header(3, "내 취약점 진단", "출제 가능성 점수 20점 이상인 개념을 문제로 확인해요. 찍어서 맞힌 것은 '헷갈림'으로 봐요.")
    ensure_questions()
    questions = list(st.session_state["questions"].values())
    pct = _pct()
    grading = st.session_state["grading"]
    failed = st.session_state["grade_failed"]
    if st.session_state["q_failed"]:
        st.warning("문제를 만들지 못해 진단에서 뺀 개념: " + ", ".join(st.session_state["q_failed"]))
    n_essay = sum(1 for q in questions if q["kind"] == ESSAY)
    done_all = bool(questions) and all(q["concept_id"] in grading for q in questions)
    if done_all:
        counts = {s: sum(1 for q in questions if grading[q["concept_id"]]["status"] == s) for s in ("앎", "헷갈림", "모름")}
        C.stats(list(counts.items()))
    if failed:
        codes = st.session_state.get("grade_fail_codes", {})
        code = next((c for c in ("E-06", "E-07", "E-08") if c in codes.values()), "E-08")
        st.error(f"서술형 {len(failed)}문제를 채점하지 못했어요. {C.ERRORS[code]} ({code})")
        if st.session_state["grade_error"]:
            with st.expander("자세한 오류"):
                st.code(st.session_state["grade_error"][:2000])

    n_done = sum(1 for q in questions if answered(q))
    st.progress(n_done / max(1, len(questions)),
                text=f"답한 문제 {n_done} / {len(questions)} · 객관식 {len(questions) - n_essay} · 서술형 {n_essay}")
    if st.session_state["from_sample"] and not grading and n_done < len(questions):
        st.caption("샘플로 둘러보는 중이라면 '예시 답 채우기'로 바로 채점까지 가 볼 수 있어요.")
        if st.button("예시 답 채우기 (샘플 체험용)"):
            fill_examples(questions)
            st.rerun()

    for i, q in enumerate(questions, start=1):
        _card(i, q, pct[q["concept_id"]], grading, failed)

    if not done_all or failed:
        st.caption("모든 문제에 답해야 채점해요. 모르면 '모르겠어요'를 고르면 돼요.")
        label = "채점 못한 문제 다시 채점" if failed else "채점하기"
        if st.button(label, type="primary"):
            if failed:
                grade(questions, only=failed)
                st.rerun()
            missing = [f"Q{i}" for i, q in enumerate(questions, start=1) if not answered(q)]
            if missing:
                st.session_state["show_missing"] = True
                st.session_state["missing_labels"] = missing
                st.rerun()  # 카드가 버튼보다 먼저 그려지므로 다시 그려 카드 아래 표시를 바로 보이게
            st.session_state["show_missing"] = False
            st.session_state["missing_labels"] = []
            grade(questions)
            st.rerun()
        if st.session_state["show_missing"] and st.session_state["missing_labels"]:
            st.markdown(f":red[아직 답하지 않은 문제: {', '.join(st.session_state['missing_labels'])}]")
        if failed and st.button("채점 못한 문제는 빼고 공부 순서 보기"):
            st.session_state["skip_failed"] = True
            st.session_state["step"] = 4
            st.rerun()
    if done_all and not failed:
        if st.button("공부 순서 보기", type="primary"):
            st.session_state["step"] = 4
            st.rerun()
