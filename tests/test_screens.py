"""T-51~T-53 분석 중 안내 유지·헷갈린 점 적은 '복습만' 개념 펼치기·채점 실패 원인별 문구."""
from streamlit.testing.v1.element_tree import Expander

from tests.test_app_flow import new_app, run_to_s03


def _html_outside_expanders(node) -> list[str]:
    out = []
    for child in getattr(node, "children", {}).values():
        if isinstance(child, Expander):
            continue
        if getattr(child, "type", "") == "html":
            out.append(child.proto.body)
        out.extend(_html_outside_expanders(child))
    return out


def test_t51_notices_survive_rerun():
    at = new_app()
    at.button(key="bt_sample").click().run()
    at.session_state["notices"] = ["녹음에서 강조한 말을 찾지 못했어요. 자료만으로 점수를 계산했어요 (E-10)"]
    at.run()
    assert any("E-10" in w.value for w in at.warning)


def test_t52_confusion_concept_open_even_in_review_only():
    at = run_to_s03(new_app())
    at.button(key="bt_example").click().run()
    at.button(key="bt_grade").click().run()
    at.button(key="bt_to4").click().run()
    conf = [c for c, v in at.session_state["confusion"].items() if v and at.session_state["guessed"].get(c)]
    assert conf
    prios = at.session_state["priorities"]
    for p in prios:
        if p["concept_id"] in conf:
            p["action"] = "복습만"
    at.session_state["priorities"] = prios
    at.run()
    outside = " ".join(_html_outside_expanders(at.main))
    assert "💬 내가 헷갈린 점</b>" in outside


def test_t53_failure_message_by_cause():
    # AppTest가 앱 모듈을 새로 읽으므로 화면 모듈이 쓰는 llm으로 만든다
    from screens import common
    from screens.common import ERR, error_of
    llm = common.llm
    assert error_of(llm.KeyMissingError("x")) == ("E-06", ERR["E-06"])
    assert error_of(llm.ConnectionFailError("x")) == ("E-07", ERR["E-07"])
    assert error_of(llm.BadJSONError("x")) == ("E-08", ERR["E-08"])
    assert error_of(ValueError("x"))[0] == "UNKNOWN"
