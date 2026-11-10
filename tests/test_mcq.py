# T-18~T-24 객관식·진단 대상·문제 형식·다른 개념 목록·답 없음 이유, T-40 샘플 예시 답
import pytest

from core import diagnose
from core.diagnose import (ESSAY, MCQ, choose_kind, diag_targets, example_answers, grade_essay, grade_mcq,
                           is_answered, other_concepts_text, shuffle_mcq, validate_mcq)

GOOD = {"question": "삭제 과정으로 옳은 것은?", "choices": ["① 가", "② 나", "③ 다", "④ 라"], "answer_index": 0,
        "explanation": "가가 맞다(p.16).", "source_pages": [16, 99]}


def test_t18_mcq_validation():
    bad = [dict(GOOD, choices=["가", "나", "다"]), dict(GOOD, choices=["가", "가", "다", "라"]),
           dict(GOOD, answer_index=4), dict(GOOD, question="")]
    assert all(validate_mcq(b, [16]) is None for b in bad)
    q = validate_mcq(GOOD, [16])
    assert q["choices"] == ["가", "나", "다", "라"] and q["source_pages"] == [16]


def test_t19_shuffle():
    q = validate_mcq(GOOD, [16])
    a, b = shuffle_mcq(q), shuffle_mcq(q)
    assert a["choices"] == b["choices"] and a["answer"] == "가" and a["choices"][a["answer_index"]] == "가"
    spots = set()
    for i in range(40):
        qi = validate_mcq(dict(GOOD, question=f"문제 번호 {i} 에 대한 설명은?"), [16])
        spots.add(shuffle_mcq(qi)["answer_index"])
    assert len(spots) >= 3


def test_t20_mcq_grading():
    q = shuffle_mcq(validate_mcq(GOOD, [16]))
    r = q["answer_index"]
    w = (r + 1) % 4
    assert (grade_mcq(q, r, False)["status"], grade_mcq(q, r, False)["score"]) == ("앎", 10)
    g = grade_mcq(q, r, True)
    assert (g["status"], g["score"], g["error_type"]) == ("헷갈림", 5, "찍어서 맞힘")
    g = grade_mcq(q, w, False)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "오답")
    g = grade_mcq(q, None, False)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "무응답")


def test_t21_targets_and_kind():
    scores = [{"concept_id": c, "pct": p} for c, p in [("a", 100), ("b", 40), ("c", 20), ("d", 19), ("e", 0)]]
    assert diag_targets(scores) == ["a", "b", "c"]
    assert choose_kind(50, "섞어서") == ESSAY and choose_kind(49, "섞어서") == MCQ
    assert choose_kind(90, "모두 객관식") == MCQ and choose_kind(10, "모두 서술형") == ESSAY


def test_t22_mcq_fallback(monkeypatch, material, analysis):
    c = analysis["concepts"][0]
    answers = iter([{"question": "옳은 것은?", "choices": ["하나"], "answer_index": 0},
                    {"question": "과정을 쓰고 이유를 쓰시오.", "answer": "답이다.",
                     "rubric": [{"point": "과정", "score": 5}, {"point": "이유", "score": 5}], "source_pages": []}])
    monkeypatch.setattr(diagnose, "ask_json", lambda *a, **k: next(answers))
    q = diagnose.make_question(c, MCQ, material, analysis["meta"], "(없음)")
    assert q["kind"] == ESSAY


def test_t23_other_concepts():
    from core.diagnose import build_prompt
    others = other_concepts_text(["힙 삽입", "힙 삭제", "순회"], "힙 삽입")
    for kind in (ESSAY, MCQ):
        p = build_prompt(kind, "힙 삽입", "=== 페이지 1 ===\n글", others)
        seg = p.split("<other_concepts>")[-1].split("</other_concepts>")[0]
        assert "- 힙 삭제" in seg and "- 순회" in seg and "힙 삽입" not in seg
    assert other_concepts_text(["힙 삽입"], "힙 삽입") == "(없음)"


def test_t24_no_answer_reasons(material, analysis):
    c = analysis["concepts"][0]
    eq = {"kind": ESSAY, "question": "q", "answer": "a", "rubric": [{"point": "x", "score": 10}]}
    mq = shuffle_mcq(validate_mcq(GOOD, [16]))
    r1 = grade_essay(eq, "  ", False, material, analysis["meta"], c)
    r2 = grade_essay(eq, "", True, material, analysis["meta"], c)
    r3, r4 = grade_mcq(mq, -1, False), grade_mcq(mq, None, False)
    for r in (r1, r2, r3, r4):
        assert (r["score"], r["status"], r["error_type"]) == (0, "모름", "무응답")
    assert "비워 두어" in r1["reason"] and "'모르겠어요'를 골라" in r2["reason"]
    assert "'모르겠어요'를 골라" in r3["reason"] and "고르지 않아" in r4["reason"]


def test_t40_example_answers():
    qs = {}
    for i in range(6):
        if i % 2 == 0:
            qs[f"c{i}"] = {"kind": ESSAY, "question": "q", "answer": "첫 문장이다. 둘째 문장이다.",
                           "rubric": [{"point": "x", "score": 10}]}
        else:
            qs[f"c{i}"] = shuffle_mcq(validate_mcq(dict(GOOD, question=f"객관식 {i} 문제는?"), [16]))
    ex = example_answers(qs)
    assert ex["c0"]["answer"] == "첫 문장이다. 둘째 문장이다."
    assert ex["c2"]["answer"] == "첫 문장이다." and ex["c4"]["dont_know"] is True
    statuses = []
    for cid in ("c1", "c3", "c5"):
        v = ex[cid]
        statuses.append(grade_mcq(qs[cid], v["choice"], v["guessed"])["status"])
    assert statuses == ["앎", "헷갈림", "모름"] and ex["c3"]["confusion"] == diagnose.EXAMPLE_CONFUSION
    for cid, q in qs.items():
        v = ex[cid]
        assert is_answered(q, v.get("answer"), v.get("dont_know"), v.get("choice"))


@pytest.mark.parametrize("choice,ok", [(None, False), (7, False), (-1, True), (2, True)])
def test_t32_mcq_answered(choice, ok):
    q = shuffle_mcq(validate_mcq(GOOD, [16]))
    assert is_answered(q, None, False, choice) is ok
