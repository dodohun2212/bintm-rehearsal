"""T-51 분석 중 안내 유지, T-52 헷갈린 점을 적은 '복습만' 개념 펼치기, T-53 채점 실패 원인별 문구."""
from core.priority import split_review
from tests.test_privacy_robust import _app_func


def test_t51_notices_kept():
    run = _app_func("run_analysis")
    assert "st.warning(" not in run
    for code in ("E-05", "E-10", "E-13"):
        assert code in run
    assert run.count("notices.append(") >= 3 and '"notices": notices' in run
    s02 = _app_func("s02")
    assert 's["notices"]' in s02 and "st.warning(" in s02


def test_t52_review_split():
    rows = [{"concept_id": c} for c in ("a", "b", "c")]
    opened, folded = split_review(rows, ["b"])
    assert [r["concept_id"] for r in opened] == ["b"] and [r["concept_id"] for r in folded] == ["a", "c"]
    opened, folded = split_review(rows, [])
    assert opened == [] and len(folded) == 3
    assert "split_review(" in _app_func("s04")


def test_t53_grade_failure_message():
    s03 = _app_func("s03")
    box = next(line for line in s03.splitlines() if "채점하지 못했어요" in line and "st.error" in line)
    assert "(E-08)" not in box and "{code}" in box
    assert "grade_error_code" in s03
    assert "error_code(" in _app_func("grade_now")
