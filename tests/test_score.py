"""T-01~T-07, T-14, T-15 점수·우선순위·인용·페이지 검사."""
from core.diagnose import status_from_score
from core.priority import compute_priorities
from core.schemas import parse_pages
from core.score import WEIGHTS, compute_scores
from core.utterances import clean_utterances
from tests.helpers import sample

TOP3 = {"이진 트리의 순회", "힙의 삭제 연산", "힙의 삽입 연산"}


def _c(cid="c1", pages=(5,), **kw):
    d = {"id": cid, "name": f"개념{cid}", "pages": list(pages), "in_objectives": False, "has_example": False,
         "has_exercise": False, "exercise_numbers": []}
    d.update(kw)
    return d


def test_t01_sample_top3_and_last():
    s = sample()
    names = [r["name"] for r in s["scores"]]
    assert set(names[:3]) == TOP3
    assert names[-1] == "이진 탐색 트리의 삭제"
    assert [r["pct"] for r in s["scores"][:3]] == [100, 98, 96]


def test_t01_deterministic():
    s = sample()
    again = compute_scores(s["concepts"], s["utterances"], s["meta"])["scores"]
    assert [(r["name"], r["pct"]) for r in again] == [(r["name"], r["pct"]) for r in s["scores"]]


def test_t02_negative_clipped():
    utts = [{"concept_id": "c1", "quote": "q", "type": "deferral", "strength": 2}] * 3
    rows = compute_scores([_c("c1"), _c("c2", pages=(6, 7))], utts, [1])["scores"]
    r1 = next(r for r in rows if r["concept_id"] == "c1")
    assert r1["raw"] == 0 and r1["pct"] == 0


def test_t03_meta_pages_excluded():
    rows = compute_scores([_c("c1", pages=(2, 3, 15, 20))], [], [2, 3, 20])["scores"]
    assert len(rows[0]["body_pages"]) == 1


def test_t04_repeated_utterance_doubles():
    one = [{"concept_id": "c1", "quote": "꼭", "type": "emphasis", "strength": 3}]
    a = compute_scores([_c("c1", pages=())], one, [1])["scores"][0]["raw"]
    b = compute_scores([_c("c1", pages=())], one * 2, [1])["scores"][0]["raw"]
    assert b == 2 * a == 2 * WEIGHTS["emphasis"]


def test_t05_unknown_type_ignored():
    tr = "이건 꼭 알아두세요."
    utts = clean_utterances({"utterances": [{"concept_id": "c1", "quote": "이건 꼭 알아두세요.", "type": "foo",
                                             "strength": 3}]}, tr, ["c1"])
    assert utts == []
    rows = compute_scores([_c()], [{"concept_id": "c1", "quote": "x", "type": "foo", "strength": 3}], [1])
    assert rows["scores"][0]["raw"] == 1.0


def test_t06_priorities():
    scores = [{"concept_id": "a", "name": "힙 삭제", "pct": 97}, {"concept_id": "b", "name": "순회", "pct": 100},
              {"concept_id": "c", "name": "힙 삽입", "pct": 96}, {"concept_id": "d", "name": "우선순위 큐", "pct": 50}]
    grading = {"a": {"status": "모름"}, "b": {"status": "헷갈림"}, "c": {"status": "앎"}}
    pr = {p["concept_id"]: p for p in compute_priorities(scores, grading)}
    assert [pr[k]["priority"] for k in "abcd"] == [97, 50, 0, 25]
    assert pr["a"]["action"] == "지금 당장" and pr["d"]["action"] == "다음" and pr["c"]["action"] == "복습만"
    assert pr["d"]["status"] == "진단 안 함"


def test_t07_status():
    assert [status_from_score(x) for x in (8, 7, 4, 3, 0)] == ["앎", "헷갈림", "헷갈림", "모름", "모름"]


def test_t14_quote_must_exist():
    tr = "오늘은 힙을 합니다. 이건 꼭   알아두세요."
    raw = {"utterances": [
        {"concept_id": "c1", "quote": "이건 꼭 알아두세요.", "type": "emphasis", "strength": 3},
        {"concept_id": "c1", "quote": "대본에 없는 말", "type": "emphasis", "strength": 3},
    ]}
    out = clean_utterances(raw, tr, ["c1"])
    assert len(out) == 1 and out[0]["quote"] == "이건 꼭 알아두세요."


def test_t15_page_range():
    from core.explain import clean_explanation
    ex = clean_explanation({"source_pages": [3, 99], "explanation": "x"}, "c1", list(range(1, 21)), "", "모름", None)
    assert ex["source_pages"] == [3]
    assert parse_pages(["p.5", "3-4", 5.0, "x"]) == [5, 3, 4]
