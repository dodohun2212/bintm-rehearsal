"""T-01~T-05, T-14, T-15 점수 규칙."""
from core.schemas import keep_pages
from core.score import compute_scores, detect_meta_pages, is_meta_by_rule
from core.utterances import clean_utterances


def test_t01_top3_and_bst_delete_last(sample_analysis):
    rows = sample_analysis["scores"]["scores"]
    top3 = {r["name"] for r in rows[:3]}
    assert top3 == {"이진 트리의 순회", "힙의 삭제 연산", "힙의 삽입 연산"}
    assert rows[-1]["name"] == "이진 탐색 트리의 삭제"
    by = {r["name"]: r for r in rows}
    assert by["이진 트리의 순회"]["raw"] == 13.0 and by["이진 트리의 순회"]["pct"] == 100
    assert abs(by["힙의 삭제 연산"]["raw"] - 12.7) < 1e-6 and by["힙의 삭제 연산"]["pct"] == 98
    assert abs(by["힙의 삽입 연산"]["raw"] - 12.5) < 1e-6 and by["힙의 삽입 연산"]["pct"] == 96
    assert by["이진 탐색 트리의 삭제"]["pct"] == 0


def test_sample_meta_pages(sample_analysis):
    assert sample_analysis["meta"] == [1, 2, 3, 19, 20]


def test_same_input_same_score(sample_analysis):
    a = compute_scores(sample_analysis["concepts"], sample_analysis["utts"], sample_analysis["meta"])
    assert a == sample_analysis["scores"]


def _c(cid, pages=(5,), **kw):
    d = {"id": cid, "name": f"개념{cid}", "pages": list(pages), "in_objectives": False,
         "has_example": False, "has_exercise": False, "exercise_numbers": []}
    d.update(kw)
    return d


def test_t02_negative_clipped_to_zero():
    cs = [_c("c1", in_objectives=True), _c("c2")]
    us = [{"concept_id": "c2", "quote": "다음 주", "type": "deferral", "strength": 2}] * 3
    rows = {r["concept_id"]: r for r in compute_scores(cs, us, [1])["scores"]}
    assert rows["c2"]["raw"] == 0 and rows["c2"]["pct"] == 0


def test_t03_meta_pages_excluded_from_body():
    rows = compute_scores([_c("c1", pages=[2, 3, 15, 20])], [], [2, 3, 20])["scores"]
    assert rows[0]["body_pages"] == [15]


def test_t04_repeated_quote_doubles():
    u = {"concept_id": "c1", "quote": "꼭 알아두세요.", "type": "emphasis", "strength": 3}
    one = compute_scores([_c("c1", pages=[])], [u], [1])["max_raw"]
    two = compute_scores([_c("c1", pages=[])], [u, u], [1])["max_raw"]
    assert two == 2 * one


def test_t05_unknown_type_ignored():
    raw = {"utterances": [{"concept_id": "c1", "quote": "꼭 알아두세요", "type": "foo", "strength": 2}]}
    assert clean_utterances(raw, "꼭 알아두세요", [_c("c1")]) == []
    rows = compute_scores([_c("c1")], [{"concept_id": "c1", "quote": "x", "type": "foo"}], [1])["scores"]
    assert rows[0]["raw"] == 1.0


def test_t14_quote_not_in_transcript_dropped():
    raw = {"utterances": [{"concept_id": "c1", "quote": "없는 말입니다", "type": "emphasis", "strength": 3},
                          {"concept_id": "c1", "quote": "꼭  알아 두세요", "type": "emphasis", "strength": 3}]}
    out = clean_utterances(raw, "오늘은 꼭 알아두세요. 끝.", [_c("c1")])
    assert [u["quote"] for u in out] == ["꼭  알아 두세요"]


def test_t15_page_range():
    assert keep_pages([3, 99], range(1, 21)) == [3]
    assert keep_pages(["p.5", 6.0, "7-8", "x"], range(1, 21)) == [5, 6, 7, 8]


def test_meta_rule_first_line_only():
    assert is_meta_by_rule("8.6 요약\n힙 정리")
    assert not is_meta_by_rule("8.1 트리\n트리를 요약하면 계층 구조다")
    assert is_meta_by_rule("8장\n8.1 트리란?\n8.2 이진 트리\n8.3 순회\n")
    assert not is_meta_by_rule("값\n3.14 2.71\n1.41 1.73\n2.23 2.44\n")
    assert detect_meta_pages([{"n": 1, "text": "표지"}, {"n": 2, "text": "본문"}]) == [1]
