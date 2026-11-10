# T-01~T-07, T-14, T-15 점수·우선순위·인용·페이지 범위
from core.concepts import parse_pages
from core.diagnose import status_from_score
from core.priority import compute_priorities, priority_of
from core.score import compute_scores
from core.utterances import parse_utterances


def _c(cid, name, pages, **kw):
    base = {"id": cid, "name": name, "pages": pages, "in_objectives": False, "has_example": False,
            "has_exercise": False, "exercise_numbers": []}
    base.update(kw)
    return base


def test_t01_top3_sample(analysis):
    s = analysis["scores"]
    assert {r["name"] for r in s[:3]} == {"이진 트리의 순회", "힙의 삭제 연산", "힙의 삽입 연산"}
    assert s[-1]["name"] == "이진 탐색 트리의 삭제"
    assert [r["pct"] for r in s[:3]] == [100, 98, 96]


def test_t01_same_input_same_score(analysis):
    again = compute_scores(analysis["concepts"], analysis["utts"], analysis["meta"])["scores"]
    assert [(r["concept_id"], r["pct"]) for r in again] == [(r["concept_id"], r["pct"]) for r in analysis["scores"]]


def test_t02_negative_clamped():
    cs = [_c("c1", "가", [5]), _c("c2", "나", [6], in_objectives=True)]
    us = [{"concept_id": "c1", "type": "deferral", "strength": 2, "quote": "다음 주"}] * 3
    s = {r["concept_id"]: r for r in compute_scores(cs, us, [])["scores"]}
    assert s["c1"]["raw"] == 0 and s["c1"]["pct"] == 0


def test_t03_meta_pages():
    s = compute_scores([_c("c1", "가", [2, 3, 15, 20])], [], [2, 3, 20])["scores"][0]
    assert len(s["body_pages"]) == 1


def test_t04_repeat_doubles():
    cs = [_c("c1", "가", []), _c("c2", "나", [])]
    one = {"type": "emphasis", "strength": 3, "quote": "꼭"}
    s = {r["concept_id"]: r for r in compute_scores(cs, [dict(one, concept_id="c1"), dict(one, concept_id="c1"),
                                                         dict(one, concept_id="c2")], [])["scores"]}
    assert s["c1"]["raw"] == 2 * s["c2"]["raw"]


def test_t05_unknown_type_ignored():
    out = parse_utterances({"utterances": [{"concept_id": "c1", "quote": "꼭 알아두세요", "type": "foo"}]},
                           "꼭 알아두세요", ["c1"])
    assert out == []
    s = compute_scores([_c("c1", "가", [3])], [{"concept_id": "c1", "type": "foo", "quote": "x"}], [])
    assert s["scores"][0]["raw"] == 1.0


def test_t06_priority_examples():
    assert priority_of(97, "모름") == 97
    assert priority_of(100, "헷갈림") == 50
    assert priority_of(96, "앎") == 0
    assert priority_of(50, "진단 안 함") == 25
    scores = [{"concept_id": "a", "name": "A", "pct": 97}, {"concept_id": "b", "name": "B", "pct": 50}]
    rows = compute_priorities(scores, {"a": {"status": "모름"}})
    assert [r["priority"] for r in rows] == [97, 25] and rows[1]["status"] == "진단 안 함"
    assert rows[0]["action"] == "지금 당장" and rows[1]["action"] == "다음"


def test_t07_status():
    assert [status_from_score(x) for x in (8, 7, 4, 3, 0)] == ["앎", "헷갈림", "헷갈림", "모름", "모름"]


def test_t14_quote_check():
    out = parse_utterances({"utterances": [
        {"concept_id": "c1", "quote": "대본에 없는 말", "type": "emphasis", "strength": 3},
        {"concept_id": "c1", "quote": "꼭  알아 두세요", "type": "emphasis", "strength": 3}]},
        "이건 꼭 알아두세요.", ["c1"])
    assert len(out) == 1


def test_t15_page_range():
    assert parse_pages([3, 99], 20) == [3]
