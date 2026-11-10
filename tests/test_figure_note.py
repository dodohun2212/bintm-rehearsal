"""T-25~T-30 문제 그림, 그림 검사, 페이지 그림, 요약 노트, 내보내기 나누기."""
import base64

from core import diagnose, note
from core.diagnose import ESSAY, MCQ, make_question
from core.export import notes_html, study_html
from core.figure import figure_html, tree_svg, validate
from core.note import detail_level, lecture_order, make_note
from core.pageimg import page_jpeg
from tests.helpers import SAMPLE_PDF


def test_t25_validate():
    ok = [{"kind": "tree", "nodes": ["A", "B", "C", None, "D"]},
          {"kind": "array", "items": [1, 2, 3], "start": 1},
          {"kind": "table", "header": ["연산", "복잡도"], "rows": [["삽입", "O(log n)"]]}]
    assert all(validate(f) for f in ok)
    bad = [{"kind": "tree", "nodes": [None, "A"]}, {"kind": "tree", "nodes": ["A", None, "C", "D"]},
           {"kind": "tree", "nodes": ["x"] * 32}, {"kind": "array", "items": []},
           {"kind": "table", "header": ["a", "b"], "rows": [["1"]]}, {"kind": "graph"}]
    assert all(validate(f) is None for f in bad)


def test_t26_draw():
    svg = tree_svg(validate({"kind": "tree", "nodes": ["A", "B", "C", "D"]}))
    assert svg.count("<circle") == 4 and svg.count("<line") == 3
    h = figure_html(validate({"kind": "tree", "nodes": ["<b>", "B"]}))
    assert "data:image/svg+xml;base64," in h and "<svg" not in h
    inner = base64.b64decode(h.split("base64,")[1].split('"')[0]).decode()
    assert "&lt;b&gt;" in inner
    arr = figure_html(validate({"kind": "array", "items": ["90", "<x>"], "start": 1}))
    assert ">1</td>" in arr and ">2</td>" in arr and "&lt;x&gt;" in arr


def test_t27_figure_reference_retry(monkeypatch):
    replies = [{"question": "p.9 그림의 트리를 중위 순회하시오.", "answer": "답이다.", "rubric": [{"point": "p", "score": 10}]},
               {"question": "아래 트리를 중위 순회한 결과를 쓰시오.", "answer": "답이다.", "rubric": [{"point": "p", "score": 10}],
                "figure": {"kind": "tree", "nodes": ["A", "B", "C"]}}]
    prompts_seen = []

    def fake(prompt, **kw):
        prompts_seen.append(prompt)
        return replies[len(prompts_seen) - 1]

    monkeypatch.setattr(diagnose, "ask_json", fake)
    q = make_question({"id": "c1", "name": "순회"}, ESSAY, [{"n": 9, "text": "순회"}], [])
    assert q["question"].startswith("아래 트리") and q["figure"]
    assert "## 다시 만들기" in prompts_seen[1] and "## 다시 만들기" not in prompts_seen[0]

    def mcq_always_refers(prompt, **kw):
        if "03-C" in prompt.splitlines()[0]:
            return {"question": "위 그림의 트리에서 옳은 것은?", "choices": ["a", "b", "c", "d"], "answer_index": 0}
        return {"question": "순회 결과를 쓰고 이유를 쓰시오.", "answer": "답이다.", "rubric": [{"point": "p", "score": 10}]}

    monkeypatch.setattr(diagnose, "ask_json", mcq_always_refers)
    q = make_question({"id": "c1", "name": "순회"}, MCQ, [{"n": 9, "text": "순회"}], [])
    assert q["kind"] == ESSAY


def test_t28_page_image():
    data = SAMPLE_PDF.read_bytes()
    img = page_jpeg(data, 9)
    assert img and img[:2] == b"\xff\xd8"
    assert page_jpeg(data, 0) is None and page_jpeg(data, 21) is None
    assert page_jpeg(b"PK\x03\x04not a pdf", 1) is None


def test_t29_note_rules(monkeypatch):
    assert detail_level("지금 당장", 10, "모름") == "자세히"
    assert detail_level("복습만", 60, "앎") == "자세히"
    assert detail_level("복습만", 30, "모름") == "자세히"
    assert detail_level("다음", 40, "진단 안 함") == "보통"
    assert detail_level("복습만", 40, "헷갈림") == "보통"
    assert detail_level("복습만", 10, "모름") == "짧게"
    assert detail_level("복습만", 30, "앎") == "짧게"
    concepts = [{"id": "a", "pages": [1, 2]}, {"id": "b", "pages": [9]}, {"id": "c", "pages": [5, 6]}]
    assert lecture_order(concepts, [1, 2]) == ["c", "b", "a"]

    calls = []
    monkeypatch.setattr(note, "ask_json", lambda prompt, **kw: calls.append(prompt) or {
        "summary": "s다(p.5).", "key_points": ["k"] * 9, "pitfalls": ["p"] * 5, "source_pages": [5, 99]})
    c = {"id": "c1", "name": "힙", "summary": "한 줄 요약", "pages": [5]}
    short = make_note(c, "짧게", {}, None, [], [{"n": 5, "text": "x"}])
    assert short["summary"] == "한 줄 요약" and not short["from_ai"] and not calls
    g = {"score": 0, "error_type": "개념 혼동", "reason": "삭제와 혼동했다"}
    utts = [{"concept_id": "c1", "quote": "이건 꼭 알아두세요.", "type": "emphasis", "strength": 3}]
    n = make_note(c, "자세히", {"exam_pct": 90, "action": "지금 당장", "status": "모름"}, g, utts, [{"n": 5, "text": "x"}])
    assert "삭제와 혼동했다" in calls[0] and "이건 꼭 알아두세요." in calls[0]
    assert len(n["key_points"]) == 5 and len(n["pitfalls"]) == 2 and n["source_pages"] == [5]
    n2 = make_note(c, "보통", {}, None, [], [{"n": 5, "text": "x"}])
    assert len(n2["key_points"]) == 3


def _state():
    q = {"kind": ESSAY, "question": "아래 트리를 <b>중위</b> 순회하시오.", "answer": "DBEAC 순서다.",
         "rubric": [{"point": "순서", "score": 10}], "source_pages": [9],
         "figure": {"kind": "tree", "nodes": ["A", "B", "C"], "caption": None}}
    return {
        "material_name": "s.pdf", "date": "2026-11-11", "transcript_source": "paste",
        "priorities": [{"concept_id": "c1", "name": "순회", "exam_pct": 100, "status": "모름", "understanding": 0,
                        "priority": 100, "action": "지금 당장", "rank": 1}],
        "scores": [{"concept_id": "c1", "name": "순회", "pct": 100, "reasons": []}],
        "questions": {"c1": q}, "grading": {"c1": {"kind": ESSAY, "score": 2, "max": 10, "status": "모름",
                                                   "error_type": "절차 누락", "reason": "순서가 틀렸다 (p.9).",
                                                   "rubric_scores": [2]}},
        "answers": {"c1": "<script>x</script>"}, "dont_know": {}, "mcq_choice": {}, "guessed": {}, "confusion": {},
        "explanations": {"c1": {"my_gap": "순서를 혼동했다.", "explanation": "중위 순회는 LVR이다(p.9).",
                                "check_pages": [9], "source_pages": [9], "not_found": False}},
        "notes": {"c1": {"concept_id": "c1", "detail": "자세히", "summary": "노트 요약이다(p.9).", "key_points": ["k"],
                         "pitfalls": [], "source_pages": [9], "from_ai": True}},
        "concepts": [{"id": "c1", "name": "순회", "pages": [9]}], "meta": [1], "utterances": [],
    }


def test_t30_export_split():
    st = _state()
    study, notes_doc = study_html(st), notes_html(st)
    assert study.count("중위</b>") == 0 and study.count("&lt;b&gt;중위&lt;/b&gt;") == 1
    card = study.split("2. 오답노트")[1]
    assert "&lt;script&gt;" in card and "순서가 틀렸다" in card and "중위 순회는 LVR이다" in card
    assert study.count("data:image/svg+xml") == 1
    for doc in (study, notes_doc):
        assert "image/jpeg" not in doc and "#pg-" not in doc and "<script>" not in doc
    assert "노트 요약이다" in notes_doc and "노트 요약이다" not in study
