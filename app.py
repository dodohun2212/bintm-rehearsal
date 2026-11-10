"""빈틈노트 화면 (Streamlit). 계산은 core.py가 한다."""
import hashlib
import os
import re
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="빈틈노트", page_icon="📝")

# secrets 파일이 없으면 st.secrets 읽기가 예외를 내므로 try로 읽는다
try:
    _key = st.secrets.get("ANTHROPIC_API_KEY", "")
except Exception:
    _key = ""
if _key:
    os.environ["ANTHROPIC_API_KEY"] = _key

import core  # noqa: E402  (키를 환경 변수에 넣은 뒤 불러옴)

ROOT = Path(__file__).parent
FOOTER = (
    "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다. "
    "올린 자료는 분석을 위해 Anthropic 서버로 전송되고, 이 앱의 서버에는 저장하지 않아요."
)
MAX_ANALYSES = 5
STATE_COLOR = {core.KNOW: "green", core.CONFUSED: "orange", core.UNKNOWN: "red", core.NOT_DIAG: "gray"}
NUMS = "①②③④"

# 스피너를 화면 아래 가운데에 고정 (아래로 내려 둔 사람도 보게)
st.markdown(
    """<style>
[data-testid="stSpinner"] {
  position: fixed; bottom: 1.5rem; left: 50%; transform: translateX(-50%);
  z-index: 1000; background: #ffffff; padding: .6rem 1.1rem; border-radius: .6rem;
  box-shadow: 0 4px 16px rgba(0,0,0,.18);
}
</style>""",
    unsafe_allow_html=True,
)

# ---------- 상태 ----------
DEFAULTS = {
    "step": 1, "reached": 1, "analyses": 0, "result": None, "is_sample": False, "source": "",
    "questions": None, "mcq_failed": False, "answers": {}, "graded": False, "states": {},
    "explanations": {}, "auto_done": False,
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v.copy() if isinstance(v, dict) else v


def clear_widgets():
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and re.match(r"^[qg]_\d+$", k):
            del st.session_state[k]


def reset_downstream():
    """새 분석이면 진단·설명을 비운다."""
    for k in ["questions", "mcq_failed", "answers", "graded", "states", "explanations", "auto_done"]:
        v = DEFAULTS[k]
        st.session_state[k] = v.copy() if isinstance(v, dict) else v
    clear_widgets()


def reset_all():
    analyses = st.session_state.analyses  # 횟수 제한은 유지
    for k, v in DEFAULTS.items():
        st.session_state[k] = v.copy() if isinstance(v, dict) else v
    st.session_state.analyses = analyses
    clear_widgets()


def go(step: int):
    st.session_state.step = step
    st.session_state.reached = max(st.session_state.reached, step)


def esc(text: str) -> str:
    """AI가 쓴 글이 마크다운·수식으로 깨지지 않게."""
    return re.sub(r"([\\`*_\[\]<>#|~$])", r"\\\1", str(text))


def show_error(e: Exception):
    msg = e.message if isinstance(e, core.AppError) else "알 수 없는 오류가 생겼어요. 다시 시도해 주세요."
    st.error(msg)
    with st.expander("자세한 오류"):
        st.code(getattr(e, "detail", "") or repr(e))


def state_badge(state: str) -> str:
    return f":{STATE_COLOR[state]}-badge[{state}]"


# ---------- 분석 (AI 호출 1, 2는 캐시) ----------
def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@st.cache_data(show_spinner=False, max_entries=50)
def cached_concepts(key: str, _pages: list) -> dict:
    return core.run_concepts(_pages)


@st.cache_data(show_spinner=False, max_entries=50)
def cached_utterances(key: str, _concepts: list, _transcript: str) -> list:
    return core.run_utterances(_concepts, _transcript)


def run_analysis(source: str, is_sample: bool, file=None, transcript: str = ""):
    if st.session_state.analyses >= MAX_ANALYSES:
        st.warning("이 화면에서는 분석을 5번까지 할 수 있어요.")
        return
    st.session_state.analyses += 1  # 캐시로 바로 끝나도 1번으로 셈
    try:
        with st.status("분석 중…", expanded=True) as status:
            st.write("텍스트 추출 중")
            if is_sample:
                pages = core.split_marked_pages((ROOT / "samples/sample_lecture.md").read_text(encoding="utf-8"))
                transcript = (ROOT / "samples/sample_transcript.md").read_text(encoding="utf-8")
            else:
                pages = core.extract_file(file[0], file[1])
            pages = core.mask_pages(pages)
            transcript = core.mask(transcript or "")
            st.write("개념 찾는 중")
            res = cached_concepts(_hash(core.format_pages(pages)), pages)
            st.write("교수님 강조 찾는 중")
            concept_lines = "\n".join(f"{c['id']}: {c['name']}" for c in res["concepts"])
            utter = cached_utterances(_hash(concept_lines + "\n" + transcript), res["concepts"], transcript)
            st.write("점수 계산 중")
            scored = core.score_concepts(res["concepts"], utter, res["meta_pages"])
            status.update(label="분석 완료", state="complete")
    except Exception as e:  # 실패하면 횟수를 돌려준다
        st.session_state.analyses -= 1
        show_error(e)
        return
    reset_downstream()
    st.session_state.result = {"pages": pages, "scored": scored, "meta_pages": res["meta_pages"]}
    st.session_state.is_sample = is_sample
    st.session_state.source = source
    st.session_state.reached = 2
    go(2)
    st.rerun()


# ---------- ① 자료 올리기 ----------
def page_upload():
    st.title("📝 빈틈노트")
    st.markdown("**강의자료와 교수님 강조점, 메타인지 진단으로 시험 전 공부 우선순위를 정해주는 AI 서비스**")
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not has_key:
        st.error("ANTHROPIC_API_KEY가 설정되지 않았어요. README의 실행 방법을 봐 주세요.")
    up = st.file_uploader("강의자료 (PDF, PPTX · 30MB 이하)", type=["pdf", "pptx"])
    transcript = st.text_area(
        "강의 대본 (선택)",
        placeholder="교수님 말을 받아쓴 대본이 있으면 붙여 넣어 주세요. 없어도 돼요.",
        height=150,
    )
    c1, c2 = st.columns(2)
    start = c1.button("분석 시작", type="primary", width="stretch", disabled=not has_key or up is None)
    sample = c2.button("샘플 자료로 체험하기", width="stretch", disabled=not has_key)
    st.caption(f"분석은 이 화면에서 {MAX_ANALYSES}번까지 할 수 있어요. (지금 {st.session_state.analyses}번)")
    if start and up is not None:
        run_analysis(up.name, False, file=(up.name, up.getvalue()), transcript=transcript)
    elif sample:
        run_analysis("샘플: 자료구조 8주차 트리와 힙 (가상 자료)", True)


# ---------- ② 출제 포인트 레이더 ----------
def badges(s: dict) -> str:
    b = []
    if s["in_objectives"]:
        b.append("🎯학습목표")
    if s["body_pages"]:
        b.append(f"📄본문 {len(s['body_pages'])}쪽")
    if s["has_example"]:
        b.append("✏️예제")
    if s["in_exercise"]:
        b.append("📝연습문제")
    if s["emphasis_count"]:
        b.append(f"🎙️강조 {s['emphasis_count']}회")
    types = {u["type"] for u in s["utterances"]}
    if "defer" in types:
        b.append("⏭️다음에 다룸")
    if "skip" in types:
        b.append("⏭️가볍게 넘어감")
    return " · ".join(b)


def page_radar():
    scored = st.session_state.result["scored"]
    targets = core.pick_targets(scored)
    st.header("② 출제 포인트 레이더")
    st.caption(st.session_state.source)
    m1, m2, m3 = st.columns(3)
    m1.metric("찾은 개념", f"{len(scored)}개")
    m2.metric("교수님 강조", f"{sum(s['emphasis_count'] for s in scored)}회")
    m3.metric("진단할 개념", f"{len(targets)}개")

    divided = False
    for rank, s in enumerate(scored, 1):
        low = s["score"] < core.MIN_DIAG_SCORE
        if low and not divided:
            st.divider()
            st.caption("진단하지 않고 복습만으로 둬요")
            divided = True
        name = f":gray[{esc(s['name'])}]" if low else f"**{esc(s['name'])}**"
        c1, c2, c3 = st.columns([5, 3, 1.2], vertical_alignment="center")
        c1.markdown(f"{rank}. {name}  \n:gray[{badges(s)}]")
        c2.progress(s["score"] / 100)
        c3.markdown(f":gray[{s['score']}점]" if low else f"**{s['score']}점**")
    st.caption("출제 가능성 점수는 가장 높은 개념을 100점으로 맞춘 비교용 점수예요. 확률이 아니며 실제 출제를 보장하지 않습니다.")

    with st.expander("점수 내역과 교수님이 한 말"):
        for s in scored:
            pages = ", ".join(f"p.{p}" for p in s["pages"]) or "없음"
            st.markdown(f"**{esc(s['name'])}** · 등장 쪽: {pages} · 합계 {s['raw']:.2f} → {s['score']}점")
            lines = [f"- {label} {pts:+g}" for label, pts in s["reasons"]] or ["- 신호 없음"]
            st.markdown("\n".join(lines))
            for u in s["utterances"]:
                st.markdown(f"> 🎙️ “{esc(u['quote'])}” — {core.UTTER_LABELS[u['type']]}")

    st.button(f"{len(targets)}개 개념 진단하기 →", type="primary", width="stretch", on_click=go, args=(3,))


# ---------- ③ 내 취약점 진단 ----------
def fill_example():
    """샘플 체험용: 위젯 키와 answers에 함께 넣는다 (위젯을 그리기 전, 콜백에서)."""
    ex = core.example_answers(st.session_state.questions)
    for i, a in ex.items():
        st.session_state[f"q_{i}"] = a["choice"]
        if a["choice"] >= 0:
            st.session_state[f"g_{i}"] = a["guessed"]
        else:
            st.session_state.pop(f"g_{i}", None)
    st.session_state.answers = ex


def grade_all():
    st.session_state.states = core.diagnose(st.session_state.questions, st.session_state.answers)
    st.session_state.graded = True


def skip_to_plan():
    st.session_state.questions = st.session_state.questions or []
    st.session_state.graded = True
    go(4)


def show_results(questions: list):
    answers = st.session_state.answers
    states = [core.grade(q, answers.get(i)) for i, q in enumerate(questions)]
    m1, m2, m3 = st.columns(3)
    m1.metric("앎", f"{states.count(core.KNOW)}개")
    m2.metric("헷갈림", f"{states.count(core.CONFUSED)}개")
    m3.metric("모름", f"{states.count(core.UNKNOWN)}개")
    for i, q in enumerate(questions):
        a = answers.get(i) or {}
        with st.container(border=True):
            st.markdown(f"**Q{i + 1}. {esc(q['concept_name'])}** {state_badge(states[i])}")
            st.markdown(esc(q["question"]))
            st.markdown(f"- 내가 고른 답: {esc(core.choice_text(q, a.get('choice')))}"
                        + (" (찍었어요)" if a.get("guessed") else ""))
            st.markdown(f"- 정답: {NUMS[q['answer_index']]} {esc(q['choices'][q['answer_index']])}")
            if q.get("explanation"):
                st.markdown(f"- 해설: {esc(q['explanation'])}")


def page_diagnose():
    st.header("③ 내 취약점 진단")
    r = st.session_state.result
    targets = core.pick_targets(r["scored"])
    if not targets:
        st.info("진단할 개념이 없어요. 자료에서 시험 신호를 찾지 못했어요.")
        st.button("공부 순서 보기 →", type="primary", width="stretch", on_click=skip_to_plan)
        return

    if st.session_state.questions is None:
        if st.session_state.mcq_failed:
            if st.button("진단 문제 다시 만들기", type="primary"):
                st.session_state.mcq_failed = False
                st.rerun()
            return
        with st.spinner("진단 문제 만드는 중…"):
            try:
                st.session_state.questions = core.run_mcq(targets, r["pages"])
            except Exception as e:
                st.session_state.mcq_failed = True
                show_error(e)
                st.button("진단 문제 다시 만들기", on_click=lambda: st.session_state.update(mcq_failed=False))
                return

    questions = st.session_state.questions
    if not questions:
        st.warning("진단 문제를 만들지 못했어요. 모든 개념을 '진단 안 함'으로 두고 공부 순서를 보여 드릴게요.")
        st.button("공부 순서 보기 →", type="primary", width="stretch", on_click=skip_to_plan)
        return

    if st.session_state.graded:  # 채점이 끝났으면 결과만
        show_results(questions)
        st.button("공부 순서 보기 →", type="primary", width="stretch", on_click=go, args=(4,))
        return

    answers = st.session_state.answers
    # 위젯 값 → answers 로 옮겨 둔다 (위젯이 사라져도 답이 남게)
    for i in range(len(questions)):
        if f"q_{i}" in st.session_state:
            choice = st.session_state[f"q_{i}"]
            prev_guess = (answers.get(i) or {}).get("guessed", False)
            guessed = st.session_state.get(f"g_{i}", prev_guess) if choice is not None and choice >= 0 else False
            answers[i] = {"choice": choice, "guessed": bool(guessed)}

    done = len(questions) - len(core.unanswered(questions, answers))
    st.progress(done / len(questions), text=f"답한 문제 {done} / {len(questions)}")
    if st.session_state.is_sample:
        st.button("예시 답 채우기 (샘플 체험용)", width="stretch", on_click=fill_example)

    options = [0, 1, 2, 3, core.DONT_KNOW]
    for i, q in enumerate(questions):
        with st.container(border=True):
            st.markdown(f"**Q{i + 1}. {esc(q['concept_name'])}** · :blue[출제 점수 {q['score']}]")
            st.markdown(esc(q["question"]))
            kw = {}
            if f"q_{i}" not in st.session_state:  # 키가 없을 때만 기본값을 준다
                prev = (answers.get(i) or {}).get("choice")
                kw["index"] = options.index(prev) if prev in options else None
            choice = st.radio(
                f"Q{i + 1} 답",
                options,
                key=f"q_{i}",
                format_func=lambda v, q=q: "모르겠어요" if v == core.DONT_KNOW else f"{NUMS[v]} {esc(q['choices'][v])}",
                label_visibility="collapsed",
                **kw,
            )
            guessed = False
            if choice is not None and choice >= 0:
                kw = {} if f"g_{i}" in st.session_state else {"value": (answers.get(i) or {}).get("guessed", False)}
                guessed = st.checkbox("확신 없이 골랐어요 (찍었어요)", key=f"g_{i}", **kw)
            answers[i] = {"choice": choice, "guessed": bool(guessed)}

    if st.button("채점하기", type="primary", width="stretch"):
        missing = core.unanswered(questions, answers)
        if missing:
            st.warning(f"아직 답하지 않은 문제: {', '.join(f'Q{n}' for n in missing)}. 모르면 '모르겠어요'를 골라 주세요.")
        else:
            grade_all()
            st.rerun()


# ---------- ④ 우선순위 보완 학습 ----------
def explain(items: list):
    r = st.session_state.result
    result = core.run_explain(items, st.session_state.questions or [], st.session_state.answers, r["pages"])
    st.session_state.explanations.update(result)


def page_plan():
    st.header("④ 우선순위 보완 학습")
    r = st.session_state.result
    plan = core.build_plan(r["scored"], st.session_state.states)
    m1, m2, m3 = st.columns(3)
    for col, b in zip([m1, m2, m3], [core.NOW, core.NEXT, core.REVIEW]):
        col.metric(b, f"{sum(1 for it in plan if it['bucket'] == b)}개")

    if not st.session_state.auto_done:  # 처음 들어올 때 상위 3개 자동 설명
        st.session_state.auto_done = True
        top = core.auto_explain_targets(plan)
        if top:
            with st.spinner("보완 설명 만드는 중…"):
                try:
                    explain(top)
                except Exception as e:
                    show_error(e)

    expl = st.session_state.explanations
    for bucket in [core.NOW, core.NEXT, core.REVIEW]:
        items = [it for it in plan if it["bucket"] == bucket]
        if not items:
            continue
        st.subheader(f"{bucket} · {len(items)}개")
        for it in items:
            c = it["concept"]
            with st.container(border=True):
                st.markdown(
                    f"**{esc(c['name'])}** {state_badge(it['state'])} · 출제 점수 {c['score']} · 우선순위 {it['priority']}"
                )
                e = expl.get(c["id"])
                if e:
                    st.markdown(f"**핵심 설명**  \n{esc(e['core'])}")
                    if e.get("missed"):
                        st.markdown(f"**내가 놓친 점**  \n{esc(e['missed'])}")
                    if e.get("review_pages"):
                        st.markdown("**다시 볼 쪽** " + ", ".join(f"p.{p}" for p in e["review_pages"]))
                elif st.button("설명 보기", key=f"ex_{c['id']}"):
                    with st.spinner("보완 설명 만드는 중…"):
                        try:
                            explain([it])
                            st.rerun()
                        except Exception as err:
                            show_error(err)

    md = core.to_markdown(st.session_state.source, plan, st.session_state.questions or [],
                          st.session_state.answers, expl)
    st.download_button("결과 내려받기 (.md)", data=md.encode("utf-8"), file_name="빈틈노트_결과.md",
                       mime="text/markdown", type="primary", width="stretch")
    st.button("다른 자료로 다시", width="stretch", on_click=reset_all)


# ---------- 사이드바와 라우팅 ----------
LABELS = {1: "① 자료 올리기", 2: "② 출제 포인트 레이더", 3: "③ 내 취약점 진단", 4: "④ 우선순위 보완 학습"}
if st.session_state.result is None:
    st.session_state.step, st.session_state.reached = 1, 1
reachable = st.session_state.reached

with st.sidebar:
    st.markdown("### 📝 빈틈노트")
    for n, label in LABELS.items():
        st.button(label, key=f"nav_{n}", width="stretch", disabled=n > reachable,
                  type="primary" if n == st.session_state.step else "secondary", on_click=go, args=(n,))
    st.divider()
    st.button("처음부터", width="stretch", on_click=reset_all)
    st.caption(f"모델: {core.MODEL}")

{1: page_upload, 2: page_radar, 3: page_diagnose, 4: page_plan}[st.session_state.step]()

st.divider()
st.caption(FOOTER)
