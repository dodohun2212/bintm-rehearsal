"""T-07, T-39, T-55~T-63, T-68: 상태 판정·메타 첫 줄·서술형 총점·본문 인용 칩·한국 날짜·설명 없는 카드·빠른 진단 기본값·발화 중복·연습문제 지목·보기 조사."""
from datetime import date, timedelta

from core import llm
from core.cites import check_recording_marks, strip_bad_cites
from core.diagnose import ESSAY, normalize_grading, quick_default, status_from_score
from core.explain import make_explanation
from core.export import file_names, study_html
from core.guard import KST, kst_now
from core.html import NO_EXPLAIN_NOTE, choice_is, choice_obj
from core.score import is_meta_by_rule
from core.utterances import clean_utterances
from tests.test_figure_note import _state


def test_t07_status_rules():
    assert [status_from_score(s) for s in (8, 7, 4, 3, 0)] == ["앎", "헷갈림", "헷갈림", "모름", "모름"]
    assert status_from_score(6, "개념 혼동") == "모름"


def test_t39_usage_merge_counts_every_call():
    batch = llm.Usage()
    for _ in range(3):
        batch.add_call(100, 10, 1.0)
    total = llm.Usage()
    total.add_call(5, 5, 0.5)
    total.merge(batch)
    assert total.calls == 4 and total.input_tokens == 305 and total.output_tokens == 35


def test_t55_meta_first_line():
    assert is_meta_by_rule("8.6 요약\n힙")
    assert is_meta_by_rule("■ 연습문제\n1. 트리")
    assert not is_meta_by_rule("8.1 트리 요약하면 계층 구조다\n본문")


def test_t56_essay_total_is_rubric_sum_and_confusion():
    q = {"kind": ESSAY, "rubric": [{"point": "a", "score": 5}, {"point": "b", "score": 5}], "source_pages": [3]}
    g = normalize_grading({"score": 10, "rubric_scores": [3, 3]}, q, [3])
    assert g["score"] == 6 and g["status"] == "헷갈림"
    g = normalize_grading({"score": 6, "rubric_scores": [3, 3], "error_type": "개념 혼동"}, q, [3])
    assert g["status"] == "모름"


def test_t57_body_cites_checked(monkeypatch):
    assert strip_bad_cites("가(p.3). 나(p.99). 다(p.3, p.99).", [3]) == "가(p.3). 나. 다(p.3)."

    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        return {"my_gap": "틀렸다(p.42).", "explanation": "설명(p.3). 엉뚱(p.42).", "check_pages": [3, 42],
                "source_pages": [3, 42], "not_found": False, "confusion_reply": "답(p.42)."}

    monkeypatch.setattr(llm, "ask_json", fake)
    ex = make_explanation({"id": "c1", "name": "힙"}, "모름", None, {"reason": "r"}, {}, "질문", "글", [3])
    assert "p.42" not in ex["explanation"] + ex["my_gap"] + ex["confusion_reply"]
    assert ex["source_pages"] == [3] and ex["check_pages"] == [3]
    assert check_recording_marks("교수님은 '꼭 알아두세요'라고 했다(녹음). 지어낸 말이다(녹음).",
                                 ["이건 꼭 알아두세요."]).count("(녹음)") == 1


def test_t58_korean_date():
    assert KST.utcoffset(None) == timedelta(hours=9)
    assert kst_now().utcoffset() == timedelta(hours=9)
    f1, f2 = file_names(date(2026, 11, 11))
    assert f1 == "빈틈노트_공부순서_오답노트_2026-11-11.html" and f2 == "빈틈노트_요약노트_2026-11-11.html"


def test_t60_card_without_explanation_says_how():
    s = _state()
    s["explanations"] = {}
    assert NO_EXPLAIN_NOTE in study_html(s)


def test_t61_quick_diag_default():
    assert quick_default(9, from_sample=False) is True
    assert quick_default(8, from_sample=False) is False
    assert quick_default(20, from_sample=True) is False


def _c(cid, nums=()):
    return {"id": cid, "name": f"개념{cid}", "exercise_numbers": list(nums)}


def test_t62_duplicate_utterances_limited():
    u = {"concept_id": "c1", "concept_name": "x", "quote": "꼭 알아두세요.", "type": "emphasis", "strength": 3}
    once = clean_utterances({"utterances": [u, u, u]}, "오늘은 꼭 알아두세요. 끝", [_c("c1")])
    assert len(once) == 1
    twice = clean_utterances({"utterances": [u, u, u]}, "꼭 알아두세요. 그리고 꼭 알아 두세요.", [_c("c1")])
    assert len(twice) == 2


def test_t63_exercise_hint_linked_by_number():
    u = {"concept_id": None, "concept_name": "", "quote": "4번 5번은 꼭 풀어보세요.", "type": "exercise_hint",
         "strength": 3}
    out = clean_utterances({"utterances": [u]}, "자, 4번 5번은 꼭 풀어보세요.", [_c("c10", [4]), _c("c11", [5]), _c("c2", [2])])
    assert sorted(x["concept_id"] for x in out) == ["c10", "c11"]


def test_t68_choice_josa():
    assert [choice_obj(i) for i in range(4)] == ["①을", "②를", "③을", "④를"]
    assert [choice_is(i) for i in range(4)] == ["①이에요", "②예요", "③이에요", "④예요"]
