"""T-18~T-24 객관식·진단 대상·문제 형식·다른 개념 목록·답 없음 이유, T-40 샘플 예시 답."""
from collections import Counter

from core import diagnose
from core.diagnose import (MCQ, ESSAY, choose_kind, clean_mcq, diag_targets, example_answers, grade_mcq,
                           is_answered, local_grading, make_question, other_concepts_text)

GOOD = {"question": "삭제 뒤 내려갈 때 비교하는 대상은?", "choices": ["① 더 큰 자식", "② 왼쪽 자식", "③ 부모", "④ 형제"],
        "answer_index": 0, "explanation": "자료는 더 큰 자식과 비교한다고 한다(p.16).", "source_pages": [16, 99]}


def test_t18_mcq_validation():
    q = clean_mcq(GOOD, range(1, 21))
    assert q and q["choices"][q["answer_index"]] == "더 큰 자식"
    assert all(not c.startswith(("①", "②")) for c in q["choices"])
    assert q["source_pages"] == [16]
    bad = [dict(GOOD, choices=["a", "b", "c"]), dict(GOOD, choices=["a", "a", "b", "c"]),
           dict(GOOD, answer_index=4), dict(GOOD, question="")]
    assert all(clean_mcq(b, range(1, 21)) is None for b in bad)


def test_t19_shuffle():
    a = clean_mcq(GOOD, range(1, 21))
    b = clean_mcq(GOOD, range(1, 21))
    assert a["choices"] == b["choices"]
    positions = Counter()
    for i in range(40):
        q = clean_mcq(dict(GOOD, question=f"문제 {i}", choices=["정답", "오답1", "오답2", "오답3"]), [1])
        assert q["choices"][q["answer_index"]] == "정답"
        positions[q["answer_index"]] += 1
    assert len(positions) >= 3


def test_t20_mcq_grading():
    q = {"kind": MCQ, "choices": ["a", "b", "c", "d"], "answer_index": 2}
    g = [grade_mcq(q, 2, False), grade_mcq(q, 2, True), grade_mcq(q, 0, False), grade_mcq(q, None, False)]
    assert [(x["status"], x["score"]) for x in g] == [("앎", 10), ("헷갈림", 5), ("모름", 0), ("모름", 0)]
    assert g[2]["error_type"] == "오답" and g[3]["error_type"] == "무응답"


def test_t21_targets_and_kind():
    scores = [{"concept_id": str(p), "pct": p} for p in (100, 40, 20, 19, 0)]
    assert diag_targets(scores) == ["100", "40", "20"]
    assert choose_kind(50) == ESSAY and choose_kind(49) == MCQ
    assert choose_kind(90, "모두 객관식") == MCQ and choose_kind(10, "모두 서술형") == ESSAY


def test_t22_mcq_fallback_to_essay(monkeypatch):
    calls = []

    def fake(prompt, max_tokens=0, thinking=False, usage=None):
        calls.append(prompt[:20])
        if "03-C" in prompt.splitlines()[0]:
            return {"question": "q", "choices": ["하나뿐"], "answer_index": 0}
        return {"question": "서술형 문제", "answer": "답이다.", "rubric": [{"point": "p", "score": 10}],
                "source_pages": [5]}

    monkeypatch.setattr(diagnose, "ask_json", fake)
    q = make_question({"id": "c1", "name": "힙"}, MCQ, [{"n": 5, "text": "힙"}], ["힙"])
    assert q["kind"] == ESSAY and q["question"] == "서술형 문제"


def test_t23_other_concepts_in_prompt():
    from core.diagnose import _prompt
    text = _prompt(ESSAY, {"name": "힙의 삽입"}, [{"n": 1, "text": "x"}], ["힙의 삽입", "힙의 삭제", "순회"])
    block = text.split("<other_concepts>")[-1].split("</other_concepts>")[0]
    assert "- 힙의 삭제" in block and "- 순회" in block and "힙의 삽입" not in block
    assert other_concepts_text(["힙의 삽입"], "힙의 삽입") == "(없음)"
    mcq = _prompt(MCQ, {"name": "힙의 삽입"}, [{"n": 1, "text": "x"}], ["힙의 삽입", "순회"])
    assert "- 순회" in mcq.split("<other_concepts>")[-1]


def test_t24_no_answer_reasons():
    essay = {"kind": ESSAY}
    mcq = {"kind": MCQ, "choices": ["a", "b", "c", "d"], "answer_index": 0}
    gs = [local_grading(essay, "  ", False, None, False), local_grading(essay, "", True, None, False),
          local_grading(mcq, None, False, -1, False), local_grading(mcq, None, False, None, False)]
    assert all(g["score"] == 0 and g["status"] == "모름" and g["error_type"] == "무응답" for g in gs)
    assert "비워 두어" in gs[0]["reason"]
    assert "'모르겠어요'를 골라" in gs[1]["reason"] and "'모르겠어요'를 골라" in gs[2]["reason"]
    assert "고르지 않아" in gs[3]["reason"]


def test_t40_example_answers():
    qs = []
    for i in range(6):
        if i % 2 == 0:
            qs.append((f"e{i}", {"kind": ESSAY, "answer": "첫 문장이다. 둘째 문장이다.", "choices": []}))
        else:
            qs.append((f"m{i}", {"kind": MCQ, "choices": ["a", "b", "c", "d"], "answer_index": 1}))
    ex = example_answers(qs)
    assert ex["e0"] == {"answer": "첫 문장이다. 둘째 문장이다.", "dont_know": False}
    assert ex["e2"]["answer"] == "첫 문장이다."
    assert ex["e4"]["dont_know"] is True
    assert ex["m1"]["choice"] == 1 and not ex["m1"]["guessed"]
    assert ex["m3"]["guessed"] and ex["m3"]["confusion"] == diagnose.EXAMPLE_CONFUSION
    assert ex["m5"]["choice"] == 2
    q = dict(qs[1][1])
    statuses = [grade_mcq(q, ex[k]["choice"], ex[k]["guessed"])["status"] for k in ("m1", "m3", "m5")]
    assert statuses == ["앎", "헷갈림", "모름"]
    for cid, q in qs:
        a = ex[cid]
        assert is_answered(q, a.get("answer"), a.get("dont_know", False), a.get("choice"))
