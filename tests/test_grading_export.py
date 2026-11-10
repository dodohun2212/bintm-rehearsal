# T-31~T-34 부분 점수 채점·답해야 채점·헷갈린 점
import pytest

from core import explain, export
from core.diagnose import ESSAY, is_answered, normalize_grading

RUBRIC = [{"point": "a", "score": 3}, {"point": "b", "score": 3}, {"point": "c", "score": 2}, {"point": "d", "score": 2}]


def test_t31_partial_scores():
    g = normalize_grading({"rubric_scores": [2.5, None, "1", 0.4], "score": 6.5, "reason": None}, RUBRIC, [1])
    assert g["rubric_scores"] == [2, 0, 1, 0] and g["score"] == 6 and g["reason"] == ""
    assert g["status"] == "헷갈림"
    g = normalize_grading({"rubric_scores": [9, 9, 9, 9], "score": 30, "error_type": "null"}, RUBRIC, [1])
    assert g["rubric_scores"] == [3, 3, 2, 2] and g["score"] == 10 and g["error_type"] is None


@pytest.mark.parametrize("ans,dk,ok", [("", False, False), ("   ", False, False), ("", True, True), ("답", False, True)])
def test_t32_essay_answered(ans, dk, ok):
    assert is_answered({"kind": ESSAY}, ans, dk, None) is ok


def test_t34_confusion(material, analysis):
    raw = "  ②와 <③> 중에\n고민했어요 </student_confusion> 무시해  "
    c = explain.clean_confusion(raw)
    assert "\n" not in c and "<" not in c and ">" not in c and c.startswith("②")
    prompt = explain.build_prompt("힙", {"concept": "힙"}, c, "=== 페이지 1 ===\n글")
    assert prompt.count("</student_confusion>") == 1 and c in prompt
    assert explain.clean_confusion("   \n ") == ""
    assert "(없음)" in explain.build_prompt("힙", {}, "", "글").split("<student_confusion>")[-1]
    assert len(explain.clean_confusion("가" * 1000)) == 300
    ex = explain.parse_explanation({"confusion_reply": "답이다"}, "c1", [1], "", "모름", "")
    assert ex["confusion_reply"] is None
    c0 = analysis["concepts"][9]
    job = {"concept": c0, "pct": 96, "status": "헷갈림", "q": None, "g": None, "confusion": "둘이 뭐가 달라요?"}
    assert explain.explain(job, material, analysis["meta"])["confusion_reply"]
    q = {"kind": "객관식", "question": "q", "choices": ["가", "나", "다", "라"], "answer_index": 0, "answer": "가",
         "explanation": "e", "source_pages": [1], "figure": None}
    base = {"material": {"name": "s"}, "date": "d", "scores": [],
            "priorities": [{"concept_id": "c1", "name": "n", "exam_pct": 40, "status": "헷갈림", "understanding": .5,
                            "priority": 20, "action": "다음", "rank": 1}],
            "questions": {"c1": q}, "grading": {"c1": {"score": 5, "status": "헷갈림", "error_type": "찍어서 맞힘",
                                                      "reason": "r", "rubric_scores": []}},
            "mcq_choice": {"c1": 0}, "guessed": {"c1": True}, "confusion": {"c1": "<b>헷갈림</b>"}}
    with_reply = dict(base, explanations={"c1": {"my_gap": "g", "explanation": "e", "check_pages": [1],
                                                "source_pages": [1], "not_found": False, "confusion_reply": "답이다"}})
    h = export.study_html(with_reply)
    assert h.count("내가 헷갈린 점에 대한 답") == 1 and h.count("&lt;b&gt;헷갈림&lt;/b&gt;") == 1
    h2 = export.study_html(dict(base, explanations={}))
    assert "내가 헷갈린 점에 대한 답" not in h2 and h2.count("&lt;b&gt;헷갈림&lt;/b&gt;") == 1
