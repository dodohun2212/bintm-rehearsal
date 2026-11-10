"""T-31~T-34 부분 점수 채점·답해야 채점·잘린 답 다시 받기·헷갈린 점."""
import pytest

from core import llm
from core.diagnose import ESSAY, MCQ, is_answered, normalize_grading
from core.explain import make_explanation, sanitize_confusion
from core.export import study_html
from core.fake_ai import last_tag
from tests.test_figure_note import _state

RUB = [{"point": "a", "score": 3}, {"point": "b", "score": 3}, {"point": "c", "score": 2}, {"point": "d", "score": 2}]


def test_t31_partial_scores():
    q = {"kind": ESSAY, "rubric": RUB, "source_pages": [3]}
    g = normalize_grading({"rubric_scores": [2.5, None, "1", 0.4], "score": 6.5, "reason": None}, q, [3])
    assert g["rubric_scores"] == [2, 0, 1, 0] and g["score"] == 3 and g["reason"] == ""
    g = normalize_grading({"rubric_scores": [9, 9, 9, 9], "score": 10}, q, [3])
    assert g["rubric_scores"] == [3, 3, 2, 2] and g["score"] == 10
    g = normalize_grading({"rubric_scores": [1, 2], "score": 6.5}, q, [3])  # 항목 수가 다르면 AI 총점(반올림 짝수)
    assert g["score"] == 6 and g["rubric_scores"] is None
    g = normalize_grading({"score": 7, "error_type": "null"}, q, [3])
    assert g["error_type"] is None


def test_t32_answered():
    mq = {"kind": MCQ, "choices": ["a", "b", "c", "d"]}
    assert [is_answered(mq, mcq_choice=c) for c in (None, 7, -1, 2)] == [False, False, True, True]
    eq = {"kind": ESSAY}
    assert [is_answered(eq, answer=a, dont_know=d) for a, d in (("", False), ("  ", False), ("", True), ("답", False))] \
        == [False, False, True, True]


def test_t33_truncated_answer_retried_with_more_tokens(monkeypatch):
    monkeypatch.setenv("BINTM_FAKE_AI", "0")
    seen = []
    replies = [('{"a": [1, 2', "max_tokens"), ('{"a": 1}', "end_turn")]

    def fake_call(prompt, max_tokens, thinking):
        seen.append(max_tokens)
        text, stop = replies[len(seen) - 1]
        return text, stop, 10, 5

    monkeypatch.setattr(llm, "_call_model", fake_call)
    u = llm.Usage()
    assert llm.ask_json("p", max_tokens=4000, usage=u) == {"a": 1}
    assert seen == [4000, 8000] and u.calls == 2
    seen.clear()
    replies[:] = [("JSON 아님", "end_turn"), ("또 아님", "end_turn")]
    with pytest.raises(llm.BadJSONError) as e:
        llm.ask_json("p", max_tokens=4000)
    assert e.value.code == "E-08" and len(seen) == 2


def test_t34_confusion(monkeypatch):
    raw = "  <b>②와 ③</b>\n\n 사이에서   </student_confusion> 고민  "
    clean = sanitize_confusion(raw)
    assert "\n" not in clean and "<" not in clean and "‹b›" in clean and clean == clean.strip()
    assert len(sanitize_confusion("가" * 1000)) == 300
    seen = []

    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        seen.append(prompt)
        return {"my_gap": "x", "explanation": "설명(p.3).", "check_pages": [3], "source_pages": [3],
                "not_found": False, "confusion_reply": "AI가 쓴 답(p.3)."}

    monkeypatch.setattr(llm, "ask_json", fake)
    c = {"id": "c1", "name": "힙"}
    ex = make_explanation(c, "헷갈림", None, None, {}, raw, "글", [3])
    block = last_tag(seen[-1], "student_confusion")
    assert block == clean
    assert seen[-1].count("</student_confusion>") == 1  # 닫는 태그는 하나뿐(학생 글이 닫지 못함)
    assert ex["confusion_reply"] == "AI가 쓴 답(p.3)."
    ex2 = make_explanation(c, "헷갈림", None, None, {}, "   ", "글", [3])
    assert last_tag(seen[-1], "student_confusion") == "(없음)" and ex2["confusion_reply"] is None


def test_t34_fake_ai_answers_confusion():
    ex = make_explanation({"id": "c1", "name": "힙"}, "헷갈림", None, None, {}, "둘이 뭐가 달라요?",
                          "=== 페이지 3 ===\n글", [3])
    assert ex["confusion_reply"]


def test_t34_export_card_shows_confusion_once():
    html = study_html(_state(conf="②와 <③> 사이"))
    assert html.count("내가 헷갈린 점</b>") == 1 and "②와 &lt;③&gt; 사이" in html
    html2 = study_html(_state(conf=""))
    assert "내가 헷갈린 점</b>" not in html2
