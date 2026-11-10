"""T-01~T-07, T-14, T-15: 점수·메타 페이지·우선순위·상태·인용·페이지 범위."""
from core.concepts import to_pages
from core.diagnose import status_of
from core.priority import compute_priorities
from core.score import WEIGHTS, compute_scores, meta_pages
from core.utterances import clean_utterances

TOP3 = {"이진 트리의 순회", "힙의 삭제 연산", "힙의 삽입 연산"}


def _one(pages, meta=None, utter=None, **kw):
    c = {"id": "c1", "name": "개념", "pages": pages, "in_objectives": False, "has_example": False,
         "has_exercise": False, "exercise_numbers": [], **kw}
    other = {"id": "c2", "name": "기준", "pages": [5, 6], "in_objectives": True, "has_example": False,
             "has_exercise": False, "exercise_numbers": []}
    return compute_scores({"meta_pages": meta or [], "concepts": [c, other]}, utter or [])


def test_t01_sample_top3_and_bst_last(material, concepts_fx, utterances_fx, transcript):
    utter = clean_utterances(utterances_fx, transcript, {c["id"] for c in concepts_fx["concepts"]})
    s = compute_scores(concepts_fx, utter, material["pages"])["scores"]
    assert {r["name"] for r in s[:3]} == TOP3
    assert s[-1]["name"] == "이진 탐색 트리의 삭제" and s[-1]["pct"] == 0
    raw = {r["name"]: r["raw"] for r in s}
    assert raw["이진 트리의 순회"] == 13.0 and raw["힙의 삭제 연산"] == 12.7 and raw["힙의 삽입 연산"] == 12.5
    # 같은 입력이면 같은 점수
    again = compute_scores(concepts_fx, utter, material["pages"])["scores"]
    assert [(r["concept_id"], r["pct"]) for r in again] == [(r["concept_id"], r["pct"]) for r in s]


def test_sample_meta_pages_union(material, concepts_fx):
    # p.2(목차)는 "목차" 글자가 없어도 절 번호 규칙으로, p.20(요약)은 메타 단어로 잡힌다
    assert meta_pages(concepts_fx, material["pages"]) == [1, 2, 3, 19, 20]


def test_t02_negative_clipped():
    utter = [{"concept_id": "c1", "type": "deferral", "strength": 2, "quote": f"다음 주 {i}"} for i in range(3)]
    s = {r["concept_id"]: r for r in _one([10], utter=utter)["scores"]}
    assert s["c1"]["raw"] < 0 and s["c1"]["pct"] == 0


def test_t03_meta_pages_excluded():
    s = {r["concept_id"]: r for r in _one([2, 3, 15, 20], meta=[2, 3, 20])["scores"]}
    assert s["c1"]["body_pages"] == [15]


def test_t04_repeated_utterance_doubles():
    one = [{"concept_id": "c1", "type": "emphasis", "strength": 3, "quote": "꼭 알아두세요"}]
    a = {r["concept_id"]: r for r in _one([10], utter=one)["scores"]}["c1"]["raw"]
    b = {r["concept_id"]: r for r in _one([10], utter=one * 2)["scores"]}["c1"]["raw"]
    assert b - 1.0 == (a - 1.0) * 2 + 0  # 본문 1쪽(1.0)을 빼면 발화 점수가 2배
    assert b == 1.0 + 2 * WEIGHTS["emphasis"]


def test_t05_unknown_type_ignored():
    utter = [{"concept_id": "c1", "type": "foo", "strength": 3, "quote": "x"}]
    s = {r["concept_id"]: r for r in _one([10], utter=utter)["scores"]}
    assert s["c1"]["raw"] == 1.0


def test_t06_priority_examples():
    scores = [{"concept_id": "a", "name": "힙 삭제", "pct": 97}, {"concept_id": "b", "name": "순회", "pct": 100},
              {"concept_id": "c", "name": "힙 삽입", "pct": 96}, {"concept_id": "d", "name": "우선순위 큐", "pct": 50}]
    grading = {"a": {"status": "모름"}, "b": {"status": "헷갈림"}, "c": {"status": "앎"}}
    pr = {p["concept_id"]: p for p in compute_priorities(scores, grading)}
    assert [pr[k]["priority"] for k in "abcd"] == [97, 50, 0, 25]
    assert pr["a"]["action"] == "지금 당장" and pr["b"]["action"] == "지금 당장"
    assert pr["d"]["action"] == "다음" and pr["c"]["action"] == "복습만"
    assert pr["d"]["status"] == "진단 안 함"


def test_t07_status():
    assert [status_of(s) for s in (8, 7, 4, 3, 0)] == ["앎", "헷갈림", "헷갈림", "모름", "모름"]


def test_t14_quote_not_in_transcript_dropped():
    raw = {"utterances": [
        {"concept_id": "c1", "concept_name": "x", "quote": "이건 꼭 알아두세요.", "type": "emphasis", "strength": 3},
        {"concept_id": "c1", "concept_name": "x", "quote": "대본에 없는 말", "type": "emphasis", "strength": 3}]}
    out = clean_utterances(raw, "자, 이건  꼭\n알아두세요. 다음으로", {"c1"})
    assert len(out) == 1 and out[0]["quote"] == "이건 꼭 알아두세요."


def test_t15_page_range():
    assert to_pages([3, 99], 20) == [3]
