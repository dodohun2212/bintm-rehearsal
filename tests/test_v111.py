"""T-51~T-53: 분석 중 안내 유지, 헷갈린 점 적은 '복습만' 개념 펼치기, 채점 실패 원인별 문구."""
import inspect

from core.priority import split_review
from screens import s01
from tests.apphelp import all_text, click, new_app, sample_to_s03


def test_t51_notices_kept_and_drawn_on_s02():
    source = inspect.getsource(s01.run_analysis)
    assert "notices.append" in source and "st.warning" not in source  # 바로 그리지 않고 세션에 담는다
    at = new_app()
    click(at, "🧪 샘플로 체험")
    at.session_state["notices"] = ["녹음에서 강조한 말을 찾지 못했어요. 자료만으로 점수를 계산했어요 (E-10)"]
    at.run()
    assert at.session_state["step"] == 2
    assert any("(E-10)" in w.value for w in at.warning)


def test_t52_review_with_confusion_stays_open():
    review = [{"concept_id": "a"}, {"concept_id": "b"}, {"concept_id": "c"}]
    opened, folded = split_review(review, {"b": "두 보기가 헷갈려요"})
    assert [p["concept_id"] for p in opened] == ["b"]
    assert [p["concept_id"] for p in folded] == ["a", "c"]
    opened, folded = split_review(review, {"a": "   "})
    assert opened == [] and len(folded) == 3


def test_t53_grade_failure_message_by_cause():
    at = sample_to_s03(new_app())
    click(at, "예시 답 채우기 (샘플 체험용)")
    essay = next(q["concept_id"] for q in at.session_state["questions"].values() if q["kind"] == "서술형")
    at.session_state["grade_failed"] = [essay]
    at.session_state["grade_fail_codes"] = {essay: "E-07"}
    at.session_state["grade_error"] = "ConnectError: 연결 끊김"
    at.run()
    errors = " ".join(e.value for e in at.error)
    assert "서술형 1문제를 채점하지 못했어요" in errors
    assert "AI 서버와 연결이 어려워요" in errors and "(E-07)" in errors
    assert "(E-08)" not in errors
    assert "채점 못한 문제 다시 채점" in [b.label for b in at.button]
    assert "이 문제를 채점하지 못했어요" in all_text(at)
