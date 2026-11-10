"""T-01~T-07, T-14, T-15: 점수·메타 페이지·이해도·우선순위·상태 판정·인용 검사·페이지 범위."""
from core.concepts import clean_concepts
from core.schemas import keep_pages
from core.score import compute_scores, meta_pages
from core.utterances import clean_utterances, quote_in_transcript
from tests.conftest import SAMPLE_TRANSCRIPT


def _sample_scores(concepts_raw, utterances_raw, sample_material):
    concepts = clean_concepts(concepts_raw, 20)
    transcript = SAMPLE_TRANSCRIPT.read_text(encoding="utf-8")
    utts = clean_utterances(utterances_raw, transcript, {c["id"] for c in concepts["concepts"]})
    meta = meta_pages(sample_material["pages"], concepts)
    return compute_scores(concepts["concepts"], utts, meta), utts


def test_t01_top3_and_bst_delete_last(concepts_raw, utterances_raw, sample_material):
    result, _ = _sample_scores(concepts_raw, utterances_raw, sample_material)
    names = [s["name"] for s in result["scores"]]
    assert set(names[:3]) == {"이진 트리의 순회", "힙의 삭제 연산", "힙의 삽입 연산"}
    assert names[-1] == "이진 탐색 트리의 삭제"
    by_name = {s["name"]: s for s in result["scores"]}
    assert by_name["이진 트리의 순회"]["raw"] == 13.0 and by_name["이진 트리의 순회"]["pct"] == 100
    assert by_name["힙의 삭제 연산"]["pct"] == 98
    assert by_name["힙의 삽입 연산"]["pct"] == 96
    assert by_name["이진 탐색 트리의 삭제"]["pct"] == 0


def test_t01_same_input_same_scores(concepts_raw, utterances_raw, sample_material):
    a, _ = _sample_scores(concepts_raw, utterances_raw, sample_material)
    b, _ = _sample_scores(concepts_raw, utterances_raw, sample_material)
    assert a == b


def _concept(cid="c1", pages=(15,), **kw):
    base = {"id": cid, "name": f"개념{cid}", "pages": list(pages), "in_objectives": False,
            "has_example": False, "has_exercise": False, "exercise_numbers": []}
    base.update(kw)
    return base


def test_t02_negative_raw_becomes_zero():
    concepts = [_concept("c1", pages=(15,)), _concept("c2", pages=(16,))]
    utts = [{"concept_id": "c2", "quote": "다음 주", "type": "deferral", "strength": 2}] * 3
    rows = {r["concept_id"]: r for r in compute_scores(concepts, utts, [])["scores"]}
    assert rows["c2"]["raw"] == 0 and rows["c2"]["pct"] == 0


def test_t03_meta_pages_excluded_from_body():
    rows = compute_scores([_concept(pages=(2, 3, 15, 20))], [], [2, 3, 20])["scores"]
    assert rows[0]["body_pages"] == [15]


def test_t04_repeated_utterance_counts_twice():
    one = [{"concept_id": "c1", "quote": "꼭", "type": "emphasis", "strength": 3}]
    raw1 = compute_scores([_concept()], one, [])["scores"][0]["raw"]
    raw2 = compute_scores([_concept()], one * 2, [])["scores"][0]["raw"]
    assert raw1 == 2.0 and raw2 == 3.0


def test_t05_unknown_type_ignored():
    utts = [{"concept_id": "c1", "quote": "x", "type": "foo", "strength": 3}]
    assert compute_scores([_concept()], utts, [])["scores"][0]["raw"] == 1.0


def test_t14_quote_must_be_in_transcript():
    raw = {"utterances": [
        {"concept_id": "c1", "concept_name": "a", "quote": "이건 꼭 알아두세요.", "type": "emphasis", "strength": 3},
        {"concept_id": "c1", "concept_name": "a", "quote": "대본에 없는 말", "type": "emphasis", "strength": 3},
    ]}
    out = clean_utterances(raw, "자, 이건  꼭\n알아두세요. 다음", {"c1"})
    assert [u["quote"] for u in out] == ["이건 꼭 알아두세요."]
    assert quote_in_transcript("이건꼭 알아두세요", "이건 꼭 알아두세요")


def test_t15_page_range():
    assert keep_pages([3, 99], range(1, 21)) == [3]
