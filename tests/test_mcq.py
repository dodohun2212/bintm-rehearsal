"""T-18~T-24 객관식·진단 대상·문제 형식·다른 개념 목록·답 없음 이유, T-40 샘플 예시 답."""
from core import diagnose, prompts
from core.diagnose import (DONT_KNOW, ESSAY, MCQ, check_mcq, choose_kind, diag_targets, example_answers,
                           grade_mcq, is_answered, other_concepts_text, shuffle_mcq)

GOOD = {"question": "옳은 것은?", "choices": ["가", "나", "다", "라"], "answer_index": 2,
        "explanation": "다가 맞다(p.3).", "source_pages": [3], "figure": None}


def test_t18_rejects_bad_mcq():
    assert check_mcq({**GOOD, "choices": ["가", "나", "다"]}) is None
    assert check_mcq({**GOOD, "choices": ["가", "가", "다", "라"]}) is None
    assert check_mcq({**GOOD, "answer_index": 4}) is None
    assert check_mcq({**GOOD, "question": ""}) is None


def test_t18_strips_choice_numbers():
    q = check_mcq({**GOOD, "choices": ["① 가", "2. 나", "C) 다", "(4) 라"]})
    assert q["choices"] == ["가", "나", "다", "라"]


def test_t19_shuffle_is_stable_and_answer_follows():
    a = shuffle_mcq(check_mcq(GOOD), "seed-1")
    b = shuffle_mcq(check_mcq(GOOD), "seed-1")
    assert a["choices"] == b["choices"]
    assert a["choices"][a["answer_index"]] == "다"
    spots = {shuffle_mcq(check_mcq(GOOD), f"문제 {i}")["answer_index"] for i in range(40)}
    assert len(spots) >= 3


def _q(kind=MCQ, answer_index=1):
    return {"concept_id": "c1", "name": "개념", "kind": kind, "choices": ["가", "나", "다", "라"],
            "answer_index": answer_index, "answer": "모범 답안이다. 둘째 문장이다.", "question": "문제",
            "rubric": [{"point": "a", "score": 10}], "pages": [3], "figure": None}


def test_t20_mcq_grading():
    q = _q()
    g = grade_mcq(q, 1, False)
    assert (g["status"], g["score"]) == ("앎", 10)
    g = grade_mcq(q, 1, True)
    assert (g["status"], g["score"], g["error_type"]) == ("헷갈림", 5, "찍어서 맞힘")
    g = grade_mcq(q, 0, False)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "오답")
    g = grade_mcq(q, None, False)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "무응답")


def test_t21_targets_and_kind():
    scores = [{"concept_id": f"c{i}", "pct": p} for i, p in enumerate([100, 40, 20, 19, 0])]
    assert diag_targets(scores) == ["c0", "c1", "c2"]
    assert choose_kind(50, "섞어서") == ESSAY
    assert choose_kind(49, "섞어서") == MCQ
    assert choose_kind(90, "모두 객관식") == MCQ
    assert choose_kind(10, "모두 서술형") == ESSAY


def test_t22_bad_mcq_falls_back_to_essay(monkeypatch, sample_material):
    calls = []

    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        calls.append(prompt.splitlines()[0])
        if "03-C" in prompt.splitlines()[0]:
            return {"question": "옳은 것은?", "choices": ["하나뿐"], "answer_index": 0}
        return {"question": "삽입 과정을 쓰시오.", "answer": "끝에 넣고 올린다.",
                "rubric": [{"point": "끝", "score": 5}, {"point": "올림", "score": 5}], "source_pages": [15]}

    monkeypatch.setattr(diagnose.llm, "ask_json", fake)
    concept = {"id": "c10", "name": "힙의 삽입 연산", "pages": [15, 17]}
    q = diagnose.make_question(concept, MCQ, sample_material, [1], ["힙의 삽입 연산"])
    assert q["kind"] == ESSAY
    assert q["question"] == "삽입 과정을 쓰시오."
    assert any("03-A" in c for c in calls)


def test_t23_other_concepts_slot():
    text = other_concepts_text(["힙의 삽입 연산", "힙의 삭제 연산", "이진 트리의 순회"], "힙의 삽입 연산")
    filled = prompts.fill("essay", CONCEPT_NAME="힙의 삽입 연산", OTHER_CONCEPTS=text, PAGES="=== 페이지 1 ===\n힙")
    block = filled.rsplit("<other_concepts>", 1)[1].split("</other_concepts>")[0]
    assert "- 힙의 삭제 연산" in block
    assert "- 이진 트리의 순회" in block
    assert "힙의 삽입 연산" not in block
    assert other_concepts_text(["힙의 삽입 연산"], "힙의 삽입 연산") == "(없음)"
    filled_mcq = prompts.fill("mcq", CONCEPT_NAME="x", OTHER_CONCEPTS="(없음)", PAGES="p")
    assert "<other_concepts>\n(없음)\n</other_concepts>" in filled_mcq


def test_t24_no_answer_reasons(sample_material):
    essay = _q(ESSAY)
    blank = diagnose.grade_essay(essay, "  ", False, sample_material)
    dk = diagnose.grade_essay(essay, "", True, sample_material)
    mdk = grade_mcq(_q(), DONT_KNOW)
    none = grade_mcq(_q(), None)
    for g in (blank, dk, mdk, none):
        assert (g["score"], g["status"], g["error_type"]) == (0, "모름", "무응답")
    assert "비워 두어" in blank["reason"]
    assert "'모르겠어요'를 골라" in dk["reason"]
    assert "'모르겠어요'를 골라" in mdk["reason"]
    assert "고르지 않아" in none["reason"]


def test_t40_example_answers_cover_all_states():
    qs = []
    for i in range(6):
        kind = ESSAY if i % 2 == 0 else MCQ
        qs.append({**_q(kind, answer_index=i % 4), "concept_id": f"c{i}"})
    ex = example_answers(qs)
    essays = [ex[q["concept_id"]] for q in qs if q["kind"] == ESSAY]
    assert essays[0] == {"answer": "모범 답안이다. 둘째 문장이다.", "dont_know": False}
    assert essays[1] == {"answer": "모범 답안이다.", "dont_know": False}
    assert essays[2]["dont_know"] is True
    mcqs = [q for q in qs if q["kind"] == MCQ]
    graded = [grade_mcq(q, ex[q["concept_id"]]["choice"], ex[q["concept_id"]]["guessed"])["status"] for q in mcqs]
    assert graded == ["앎", "헷갈림", "모름"]
    assert ex[mcqs[1]["concept_id"]]["confusion"] == diagnose.EXAMPLE_CONFUSION
    for q in qs:
        a = ex[q["concept_id"]]
        assert is_answered(q, a.get("answer"), a.get("dont_know", False), a.get("choice"))
