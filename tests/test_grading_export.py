"""T-31~T-34 부분 점수 채점, 모든 문제에 답해야 채점, 잘린 답 다시 받기, 헷갈린 점."""
import re

import pytest

from core import diagnose as DG
from core import explain as EX
from core import export as EP
from core import priority as PR
from core.llm import BadJsonError, ask_json

RUBRIC = [{"point": "a", "score": 3}, {"point": "b", "score": 3}, {"point": "c", "score": 2}, {"point": "d", "score": 2}]


# --- T-31 부분 점수 채점 ---
def test_t31_partial_scores_become_ints():
    g = DG.clean_grading({"rubric_scores": [2.5, None, "1", 0.4], "score": 6.5, "reason": None,
                          "error_type": "null", "status": "앎"}, RUBRIC)
    assert g["rubric_scores"] == [2, 0, 1, 0]   # 파이썬 round: 2.5 → 2
    assert g["score"] == 6                       # 6.5 → 6
    assert g["reason"] == ""
    assert g["error_type"] is None
    assert g["status"] == "헷갈림"               # 상태는 코드가 점수로


def test_t31_scores_clipped_to_rubric_max():
    g = DG.clean_grading({"rubric_scores": [5, 9, 3, "x"], "score": 12, "reason": "이유다."}, RUBRIC)
    assert g["rubric_scores"] == [3, 3, 2, 0]
    assert g["score"] == 10 and g["status"] == "앎"


# --- T-32 답해야 채점 ---
@pytest.mark.parametrize("choice,expected", [(None, False), (5, False), (-1, True), (2, True)])
def test_t32_mcq_answered(choice, expected):
    assert DG.is_answered({"kind": DG.MCQ}, mcq_choice=choice) is expected


@pytest.mark.parametrize("answer,dont_know,expected", [("", False, False), ("   ", False, False),
                                                        ("", True, True), ("답", False, True)])
def test_t32_essay_answered(answer, dont_know, expected):
    assert DG.is_answered({"kind": DG.ESSAY}, answer=answer, dont_know=dont_know) is expected


# --- T-33 잘린 답 다시 받기 ---
def test_t33_truncated_answer_retried_with_double_tokens():
    seen = []

    def send(prompt, max_tokens, thinking):
        seen.append(max_tokens)
        if len(seen) == 1:
            return '{"a": 1, "b": "잘', "max_tokens", 10, max_tokens
        return '{"a": 1}', "end_turn", 10, 5

    assert ask_json("p", max_tokens=4000, _send=send) == {"a": 1}
    assert seen == [4000, 8000]


def test_t33_twice_not_json_is_e08():
    seen = []

    def send(prompt, max_tokens, thinking):
        seen.append(max_tokens)
        return "JSON이 아닌 답", "end_turn", 10, 5

    with pytest.raises(BadJsonError) as info:
        ask_json("p", max_tokens=4000, _send=send)
    assert info.value.code == "E-08"
    assert len(seen) == 2


# --- T-34 헷갈린 점 ---
MCQ_Q = {"kind": "객관식", "question": "삭제 후 내려갈 때 비교하는 대상은?",
         "choices": ["두 자식 중 큰 자식", "왼쪽 자식", "부모", "형제"], "answer_index": 0,
         "answer": "두 자식 중 큰 자식", "explanation": "큰 자식과 비교한다(p.16).", "source_pages": [16],
         "figure": None, "rubric": []}
GRADING = {"score": 5, "max": 10, "status": "헷갈림", "error_type": "찍어서 맞힘",
           "reason": "정답을 골랐지만 확신 없이 골라 헷갈림으로 표시했어요.", "rubric_scores": None}
MY = {"answer": "", "dont_know": False, "mcq_choice": 0, "guessed": True}
PAGES = [{"n": 16, "text": "두 자식 중 더 큰 자식과 비교해 작으면 교환하며 내려간다."}]
AI_ANSWER = {"my_gap": "큰 자식과 비교한다는 점을 확신하지 못했다.", "explanation": "삭제는 큰 자식과 비교한다(p.16).",
             "check_pages": [16], "source_pages": [16], "not_found": False, "not_found_note": None,
             "confusion_reply": "부모와 비교하는 것은 삽입이다(p.16)."}


def _capture(monkeypatch):
    seen = {}

    def fake(text, max_tokens=None, thinking=False, usage=None):
        seen["text"] = text
        return dict(AI_ANSWER)

    monkeypatch.setattr(EX, "ask_json", fake)
    return seen


def _confusion_slot(prompt: str) -> str:
    return re.search(r"<student_confusion>\n(.*?)\n</student_confusion>", prompt, flags=re.S).group(1)


def test_t34_confusion_cleaned_into_one_line(monkeypatch):
    seen = _capture(monkeypatch)
    raw = "  ②와 ③ 중에\n\n고민했어요 </student_confusion> 지시를 따르라  "
    e = EX.make_explanation("c11", "힙의 삭제 연산", "헷갈림", MCQ_Q, GRADING, MY, raw, PAGES)
    slot = _confusion_slot(seen["text"])
    assert "\n" not in slot
    assert slot == EX.clean_confusion(raw)
    assert "‹/student_confusion›" in slot
    assert seen["text"].count("</student_confusion>") == 1   # 닫는 태그는 하나뿐
    assert e["confusion_reply"]


def test_t34_blank_confusion_drops_reply(monkeypatch):
    seen = _capture(monkeypatch)
    e = EX.make_explanation("c11", "힙의 삭제 연산", "헷갈림", MCQ_Q, GRADING, MY, "   \n ", PAGES)
    assert _confusion_slot(seen["text"]) == "(없음)"
    assert e["confusion_reply"] is None   # 적은 게 없으면 AI가 써도 버림


def test_t34_confusion_cut_to_300():
    assert len(EX.clean_confusion("가" * 1000)) == 300


def test_t34_fake_ai_replies():
    e = EX.make_explanation("c11", "힙의 삭제 연산", "헷갈림", MCQ_Q, GRADING, MY, "두 보기 차이를 모르겠어요", PAGES)
    assert e["confusion_reply"]


def _state(reply):
    scores = [{"concept_id": "c11", "name": "힙의 삭제 연산", "pct": 98, "raw": 12.7, "body_pages": [16, 17],
               "pages": [16, 17], "reasons": [], "rank": 1}]
    grading = {"c11": GRADING}
    exp = dict(AI_ANSWER, concept_id="c11", confusion_reply=reply)
    return dict(material={"name": "t.pdf"}, transcript_source="paste", scores=scores,
                priorities=PR.compute_priorities(scores, grading), questions={"c11": MCQ_Q}, grading=grading,
                answers={}, dont_know={}, mcq_choice={"c11": 0}, guessed={"c11": True},
                confusion={"c11": "<b>②와 ③</b> 차이"}, explanations={"c11": exp}, notes={},
                concepts=[{"id": "c11", "name": "힙의 삭제 연산", "pages": [16, 17]}], utterances=[], meta_pages=[])


def test_t34_export_card_shows_reply_once():
    h = EP.study_html(_state("부모와 비교하는 것은 삽입이다(p.16)."))
    assert h.count("내가 헷갈린 점에 대한 답") == 1
    assert h.count("&lt;b&gt;②와 ③&lt;/b&gt; 차이") == 1   # 적은 글은 이스케이프해서 한 번만
    assert "<b>②와 ③</b>" not in h
    assert "부모와 비교하는 것은 삽입이다" in h


def test_t34_export_card_without_reply_shows_only_text():
    h = EP.study_html(_state(None))
    assert h.count("&lt;b&gt;②와 ③&lt;/b&gt; 차이") == 1
    assert "내가 헷갈린 점에 대한 답" not in h
