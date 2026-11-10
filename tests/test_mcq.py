"""T-18~T-24, T-40: 객관식 검사·섞기·채점, 진단 대상·형식, 실패 대체, 다른 개념 목록, 답 없음 이유, 예시 답."""
import re

import pytest

from core import diagnose as DG
from core import prompts

GOOD = {"question": "삭제 후 내려갈 때 비교 대상은?", "choices": ["① 더 큰 자식", "② 왼쪽 자식", "③ 부모", "④ 형제"],
        "answer_index": 0, "explanation": "자료는 더 큰 자식과 비교한다고 한다(p.16).", "source_pages": [16, 99]}


def test_t18_mcq_validation():
    q = DG.clean_mcq(dict(GOOD), [16, 17])
    assert all(not c.startswith(("①", "②", "③", "④")) for c in q["choices"])
    assert q["source_pages"] == [16]
    bad = [dict(GOOD, choices=["a", "b", "c"]), dict(GOOD, choices=["a", "a", "b", "c"]),
           dict(GOOD, answer_index=4), dict(GOOD, question="")]
    for b in bad:
        with pytest.raises(DG.BadQuestion):
            DG.clean_mcq(b, [16])
    assert DG.strip_number("1. 더 큰 자식") == "더 큰 자식" and DG.strip_number("A) 부모") == "부모"


def test_t19_shuffle():
    q1 = DG.clean_mcq(dict(GOOD), [16])
    q2 = DG.clean_mcq(dict(GOOD), [16])
    assert q1["choices"] == q2["choices"]  # 같은 문제는 같은 순서
    assert q1["choices"][q1["answer_index"]] == "더 큰 자식" == q1["answer"]  # 정답 글이 따라감
    spots = set()
    for i in range(40):
        q = DG.clean_mcq(dict(GOOD, question=f"문제 {i}번"), [16])
        assert q["choices"][q["answer_index"]] == "더 큰 자식"
        spots.add(q["answer_index"])
    assert len(spots) >= 3


def test_t20_mcq_grading():
    q = DG.clean_mcq(dict(GOOD), [16])
    right, wrong = q["answer_index"], (q["answer_index"] + 1) % 4
    g = DG.grade_mcq(q, right, False)
    assert (g["status"], g["score"]) == ("앎", 10)
    g = DG.grade_mcq(q, right, True)
    assert (g["status"], g["score"], g["error_type"]) == ("헷갈림", 5, "찍어서 맞힘")
    g = DG.grade_mcq(q, wrong, False)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "오답")
    g = DG.grade_mcq(q, None, False)
    assert (g["status"], g["score"], g["error_type"]) == ("모름", 0, "무응답")


def test_t21_targets_and_kind():
    scores = [{"concept_id": k, "pct": p} for k, p in zip("abcde", (100, 40, 20, 19, 0))]
    assert DG.diag_targets(scores) == ["a", "b", "c"]
    assert DG.question_kind(50, "섞어서") == "서술형" and DG.question_kind(49, "섞어서") == "객관식"
    assert DG.question_kind(90, "모두 객관식") == "객관식" and DG.question_kind(10, "모두 서술형") == "서술형"


def test_t22_mcq_fallback_to_essay(monkeypatch):
    calls = []

    def fake(text, max_tokens=None, thinking=False, usage=None):
        calls.append(text)
        if "프롬프트 03-C" in text[:80]:
            return {"question": "q", "choices": ["하나"], "answer_index": 0}
        return {"question": "서술형 문제", "answer": "답이다.", "rubric": [{"point": "a", "score": 10}],
                "source_pages": [3], "figure": None}
    monkeypatch.setattr(DG, "ask_json", fake)
    q = DG.make_question("힙", "객관식", [{"n": 3, "text": "t"}], "(없음)")
    assert q["kind"] == "서술형" and q["question"] == "서술형 문제"


def test_t23_other_concepts():
    text = DG.other_concepts_text(["힙 삽입", "힙 삭제", "순회"], "힙 삽입")
    for key in ("essay", "mcq"):
        p = prompts.fill(key, CONCEPT_NAME="힙 삽입", OTHER_CONCEPTS=text, PAGES="")
        block = re.findall(r"<other_concepts>\s*(.*?)\s*</other_concepts>", p, flags=re.S)[-1]
        assert "- 힙 삭제" in block and "- 순회" in block and "힙 삽입" not in block
    assert DG.other_concepts_text(["힙 삽입"], "힙 삽입") == "(없음)"


def test_t24_blank_reasons():
    essay = {"kind": "서술형", "question": "q", "answer": "a", "rubric": [{"point": "x", "score": 10}]}
    mcq = DG.clean_mcq(dict(GOOD), [16])
    cases = [DG.grade_essay("x", essay, "   ", []), DG.blank_grading(DG.REASON_DONT_KNOW),
             DG.grade_mcq(mcq, -1, False), DG.grade_mcq(mcq, None, False)]
    for g in cases:
        assert (g["score"], g["status"], g["error_type"]) == (0, "모름", "무응답")
    assert "비워 두어" in cases[0]["reason"]
    assert "'모르겠어요'를 골라" in cases[1]["reason"] and "'모르겠어요'를 골라" in cases[2]["reason"]
    assert "고르지 않아" in cases[3]["reason"]


def test_t40_example_answers():
    qs = {}
    for i in range(6):
        if i % 2 == 0:
            qs[f"c{i}"] = {"kind": "서술형", "question": "q", "answer": "첫 문장이다. 둘째 문장이다.",
                           "rubric": [{"point": "a", "score": 10}]}
        else:
            qs[f"c{i}"] = DG.clean_mcq(dict(GOOD, question=f"객관식 {i}"), [16])
    ex = DG.example_answers(qs)
    essays = [ex[k] for k in ("c0", "c2", "c4")]
    assert essays[0]["answer"] == "첫 문장이다. 둘째 문장이다."
    assert essays[1]["answer"] == "첫 문장이다."
    assert essays[2]["dont_know"] is True
    m = [(k, ex[k]) for k in ("c1", "c3", "c5")]
    assert m[0][1]["mcq_choice"] == qs["c1"]["answer_index"] and not m[0][1]["guessed"]
    assert m[1][1]["mcq_choice"] == qs["c3"]["answer_index"] and m[1][1]["guessed"] and m[1][1]["confusion"]
    assert m[2][1]["mcq_choice"] != qs["c5"]["answer_index"]
    statuses = [DG.grade_mcq(qs[k], a["mcq_choice"], a["guessed"])["status"] for k, a in m]
    assert statuses == ["앎", "헷갈림", "모름"]
    for k, q in qs.items():
        a = ex[k]
        assert DG.is_answered(q, a["answer"], a["dont_know"], a["mcq_choice"])
