"""T-18~T-24 객관식·진단 대상·문제 형식·다른 개념 목록·답 없음 이유, T-38 빠른 진단 대상, T-40 샘플 예시 답."""
import pytest

from core import llm
from core.diagnose import (EXAMPLE_CONFUSION, MCQ, ESSAY, diag_targets, example_answers, grade_blank, grade_mcq,
                           make_question, other_concepts_text, question_kind, shuffle_choices, validate_mcq)
from core.fake_ai import last_tag
from core import prompts

GOOD = {"question": "삭제 뒤 비교 대상은?", "choices": ["더 큰 자식", "왼쪽 자식", "부모", "형제"],
        "answer_index": 0, "explanation": "자료는 더 큰 자식과 비교한다고 쓴다(p.16).", "source_pages": [16]}


def test_t18_reject_bad_mcq():
    allowed = range(1, 21)
    assert validate_mcq(dict(GOOD, choices=["a", "b", "c"]), allowed) is None
    assert validate_mcq(dict(GOOD, choices=["a", "a", "b", "c"]), allowed) is None
    assert validate_mcq(dict(GOOD, answer_index=4), allowed) is None
    assert validate_mcq(dict(GOOD, question=""), allowed) is None
    q = validate_mcq(dict(GOOD, choices=["① 더 큰 자식", "2. 왼쪽 자식", "C) 부모", "④ 형제"]), allowed)
    assert q["choices"] == ["더 큰 자식", "왼쪽 자식", "부모", "형제"] and q["answer"] == "더 큰 자식"


def test_t19_shuffle_fixed_and_spread():
    q = validate_mcq(GOOD, range(1, 21))
    a, b = shuffle_choices(q, "c1"), shuffle_choices(q, "c1")
    assert a["choices"] == b["choices"]
    assert a["choices"][a["answer_index"]] == "더 큰 자식" == a["answer"]
    spots = {shuffle_choices(dict(q, question=f"문제 {i}"), f"c{i}")["answer_index"] for i in range(40)}
    assert len(spots) >= 3


def test_t20_grade_mcq():
    q = shuffle_choices(validate_mcq(GOOD, range(1, 21)), "c1")
    r = q["answer_index"]
    assert (grade_mcq(q, r)["status"], grade_mcq(q, r)["score"]) == ("앎", 10)
    g = grade_mcq(q, r, guessed=True)
    assert (g["status"], g["score"], g["error_type"]) == ("헷갈림", 5, "찍어서 맞힘")
    g = grade_mcq(q, (r + 1) % 4)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "오답")
    g = grade_mcq(q, None)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "무응답")


def test_t21_targets_and_kinds():
    rows = [{"concept_id": f"c{i}", "pct": p} for i, p in enumerate([100, 40, 20, 19, 0])]
    assert diag_targets(rows) == ["c0", "c1", "c2"]
    assert question_kind(50, "섞어서") == ESSAY and question_kind(49, "섞어서") == MCQ
    assert question_kind(90, "모두 객관식") == MCQ and question_kind(10, "모두 서술형") == ESSAY


def test_t38_quick_diag_top5():
    rows = [{"concept_id": f"c{i}", "pct": 100 - i * 5} for i in range(12)]
    assert diag_targets(rows, top=5) == ["c0", "c1", "c2", "c3", "c4"]


def test_t22_mcq_with_one_choice_falls_back_to_essay(monkeypatch):
    calls = []

    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        calls.append(prompt)
        if "프롬프트 03-C" in prompt:
            return {"question": "q", "choices": ["하나"], "answer_index": 0}
        return {"question": "서술형 문제를 쓰시오.", "answer": "답이다.",
                "rubric": [{"point": "a", "score": 10}], "source_pages": [5]}

    monkeypatch.setattr(llm, "ask_json", fake)
    q = make_question({"id": "c1", "name": "힙"}, MCQ, "=== 페이지 5 ===\n글", [5], "(없음)")
    assert q["kind"] == ESSAY and q["requested_kind"] == MCQ


def test_t23_other_concepts_in_prompt():
    others = other_concepts_text(["힙의 삽입 연산", "힙의 삭제 연산", "이진 트리의 순회"], "힙의 삽입 연산")
    for key in ("essay", "mcq"):
        p = prompts.fill(key, CONCEPT_NAME="힙의 삽입 연산", PAGES="글", OTHER_CONCEPTS=others)
        block = last_tag(p, "other_concepts")
        assert "- 힙의 삭제 연산" in block and "- 이진 트리의 순회" in block
        assert "힙의 삽입 연산" not in block
    assert other_concepts_text(["하나"], "하나") == "(없음)"


def test_t24_blank_reasons():
    q = {"kind": ESSAY, "source_pages": [3]}
    assert "비워 두어" in grade_blank(q, "empty")["reason"]
    assert "'모르겠어요'를 골라" in grade_blank(q, "dont_know")["reason"]
    mq = shuffle_choices(validate_mcq(GOOD, range(1, 21)), "c1")
    assert "'모르겠어요'를 골라" in grade_mcq(mq, -1)["reason"]
    assert "고르지 않아" in grade_mcq(mq, None)["reason"]
    for g in (grade_blank(q, "empty"), grade_mcq(mq, -1), grade_mcq(mq, None)):
        assert (g["score"], g["status"], g["error_type"]) == (0, "모름", "무응답")


def test_t40_example_answers_cycle():
    mq = shuffle_choices(validate_mcq(GOOD, range(1, 21)), "c1")
    eq = {"kind": ESSAY, "answer": "첫 문장이다. 둘째 문장이다."}
    qs = {"e1": eq, "e2": eq, "e3": eq, "m1": mq, "m2": mq, "m3": mq}
    ex = example_answers(qs, ["e1", "m1", "e2", "m2", "e3", "m3"])
    assert ex["e1"] == {"answer": "첫 문장이다. 둘째 문장이다.", "dont_know": False}
    assert ex["e2"] == {"answer": "첫 문장이다.", "dont_know": False}
    assert ex["e3"]["dont_know"] is True
    r = mq["answer_index"]
    assert ex["m1"] == {"mcq_choice": r, "guessed": False, "confusion": ""}
    assert ex["m2"] == {"mcq_choice": r, "guessed": True, "confusion": EXAMPLE_CONFUSION}
    assert ex["m3"]["mcq_choice"] == (r + 1) % 4
    statuses = {grade_mcq(mq, ex[k]["mcq_choice"], ex[k]["guessed"])["status"] for k in ("m1", "m2", "m3")}
    assert statuses == {"앎", "헷갈림", "모름"}


def test_t65_mcq_bad_json_falls_back_to_essay(monkeypatch):
    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        if "프롬프트 03-C" in prompt:
            raise llm.BadJSONError("못 읽음")
        return {"question": "서술형 문제를 쓰시오.", "answer": "답이다.",
                "rubric": [{"point": "a", "score": 5}, {"point": "b", "score": 5}], "source_pages": [5]}

    monkeypatch.setattr(llm, "ask_json", fake)
    q = make_question({"id": "c1", "name": "힙"}, MCQ, "글", [5], "(없음)")
    assert q["kind"] == ESSAY
    from core.diagnose import ERROR_TYPES
    assert "계산 실수" in ERROR_TYPES


def test_essay_failure_raises(monkeypatch):
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {"question": ""})
    with pytest.raises(llm.BadJSONError):
        make_question({"id": "c1", "name": "힙"}, ESSAY, "글", [5], "(없음)")
