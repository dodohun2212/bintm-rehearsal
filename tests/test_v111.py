"""T-51~T-53 분석 중 안내 유지, 헷갈린 점 적은 '복습만' 개념 펼치기, 채점 실패 원인별 문구."""
import ast

from conftest import ROOT
from core.llm import BadJsonError, ConnectError, KeyMissingError, error_info
from core.priority import split_review

APP = (ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(APP)


def _body(name: str) -> str:
    fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(APP, fn)


# --- T-51 분석 중 안내 유지 ---
def test_t51_notices_kept_for_s02():
    run = _body("run_analysis")
    for code in ("E-05", "E-10", "E-13"):
        assert f'notices.append(("{code}"' in run
    assert "st.warning" not in run          # 바로 그리지 않는다
    assert "ss.notices = notices" in run
    s02 = _body("page_s02")
    assert "ss.notices" in s02 and "st.warning" in s02


# --- T-52 헷갈린 점을 적은 '복습만' 개념 ---
REVIEW = [{"concept_id": c} for c in ("c1", "c2", "c3")]


def test_t52_confusion_concept_unfolded():
    shown, folded = split_review(REVIEW, {"c2": "두 보기 차이를 모르겠어요"})
    assert [p["concept_id"] for p in shown] == ["c2"]
    assert [p["concept_id"] for p in folded] == ["c1", "c3"]


def test_t52_no_confusion_all_folded():
    shown, folded = split_review(REVIEW, {"c1": "   "})
    assert shown == [] and len(folded) == 3
    shown, folded = split_review(REVIEW, {})
    assert shown == [] and len(folded) == 3


# --- T-53 채점 실패 원인별 문구 ---
def test_t53_error_codes_by_cause():
    assert error_info(KeyMissingError("x"))[0] == "E-06"
    assert error_info(ConnectError("x"))[0] == "E-07"
    assert error_info(BadJsonError("x"))[0] == "E-08"
    assert error_info(RuntimeError("x"))[0] == "E-07"
    for code in ("E-06", "E-07", "E-08"):
        assert error_info(type("X", (), {})()) and code  # 문구 표가 있음
    assert all(error_info(e)[1] for e in (KeyMissingError(), ConnectError(), BadJsonError()))


def test_t53_app_uses_error_info_not_fixed_code():
    assert '"(E-08)"' not in APP and "(E-08)" not in APP
    assert "error_info(first_err)" in _body("grade_now")
    s03 = _body("page_s03")
    assert "ss.grade_error" in s03 and "채점하지 못했어요" in s03
