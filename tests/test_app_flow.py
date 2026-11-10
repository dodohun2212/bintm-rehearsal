"""T-54 화면 흐름: 샘플 체험 → 진단 → 예시 답 → 채점 → 공부 순서 → 요약 노트 → ⑤ (AppTest, 가짜 AI). T-37·T-66 화면 부분."""
import streamlit as st
from streamlit.testing.v1 import AppTest

from tests.conftest import ROOT

APP = str(ROOT / "app.py")


def new_app() -> AppTest:
    st.cache_resource.clear()  # 앞 테스트가 저장한 샘플 문제를 꺼내지 않게
    st.cache_data.clear()
    at = AppTest.from_file(APP, default_timeout=60)
    at.run()
    return at


def run_to_s03(at: AppTest) -> AppTest:
    at.button(key="bt_sample").click().run()
    assert at.session_state["step"] == 2, [e.value for e in at.error]
    at.button(key="bt_diag").click().run()
    assert at.session_state["step"] == 3, [e.value for e in at.error]
    return at


def test_t54_full_flow():
    at = new_app()
    assert not at.exception
    run_to_s03(at)
    qs = at.session_state["questions"]
    assert len(qs) == len(at.session_state["diag_ids"]) > 0
    kinds = {q["kind"] for q in qs.values()}
    assert kinds == {"서술형", "객관식"}
    at.button(key="bt_example").click().run()
    at.button(key="bt_grade").click().run()
    assert not at.exception
    grading = at.session_state["grading"]
    assert set(grading) == set(qs)
    statuses = {g["status"] for g in grading.values()}
    assert statuses == {"앎", "헷갈림", "모름"}
    at.button(key="bt_to4").click().run()
    assert at.session_state["step"] == 4
    ex = at.session_state["explanations"]
    prios = at.session_state["priorities"]
    now = [p["concept_id"] for p in prios if p["action"] == "지금 당장"]
    assert set(now) <= set(ex) and set(p["concept_id"] for p in prios[:3]) <= set(ex)
    # T-66: 요약 노트는 그 보기를 처음 고를 때 만든다
    assert at.session_state["notes"] == {}
    at.session_state["bt_view"] = "📒 시험 대비 요약 노트"
    at.run()
    assert not at.exception
    notes = at.session_state["notes"]
    assert notes and all(n["detail"] in ("자세히", "보통") for n in notes.values())
    at.session_state["step"] = 5
    at.run()
    assert not at.exception
    bodies = " ".join(h.proto.body for h in at.get("html"))
    assert "AI 호출 수" in bodies and "단계 · ② 문제 만들기" in bodies


def test_missing_answer_marks_cards_right_away():
    at = run_to_s03(new_app())
    at.button(key="bt_grade").click().run()
    assert at.session_state["show_missing"] is True
    assert not at.session_state["grading"]
    assert any("아직 답하지 않은 문제" in e.value for e in at.error)
    bodies = " ".join(h.proto.body for h in at.get("html"))
    assert "아직 답하지 않았어요" in bodies


def test_t37_second_session_reuses_sample_questions():
    """두 세션이 샘플 진단을 하면 두 번째는 AI 호출이 0."""
    at1 = run_to_s03(new_app())
    calls1 = at1.session_state["usage"]["calls"]
    assert calls1 > 0
    at2 = AppTest.from_file(APP, default_timeout=60)  # 캐시를 비우지 않은 두 번째 사람
    at2.run()
    run_to_s03(at2)
    assert at2.session_state["usage"]["calls"] == 0
    assert at2.session_state["questions"] == at1.session_state["questions"]
