"""T-25~T-30: 문제 그림 검사·그리기, 그림을 가리키는 문제, 원본 페이지 그림, 요약 노트, 내보내기 나누기."""
import base64
import io

from core import diagnose, note
from core.diagnose import ESSAY, MCQ
from core.export import notes_html, study_html
from core.figure import figure_html, figure_text, needs_fix, tree_svg, validate_figure
from core.pageimg import page_jpeg
from tests.conftest import SAMPLE_PDF


def test_t25_valid_figures_pass():
    assert validate_figure({"kind": "tree", "nodes": ["A", "B", "C", None, "D"]})["nodes"] == ["A", "B", "C", None, "D"]
    assert validate_figure({"kind": "array", "items": [90, 75], "start": 1})["items"] == ["90", "75"]
    assert validate_figure({"kind": "table", "header": ["a", "b"], "rows": [["1", "2"]]}) is not None


def test_t25_bad_figures_rejected():
    bad = [
        {"kind": "tree", "nodes": [None, "B"]},
        {"kind": "tree", "nodes": ["A", None, "C", "D"]},  # D의 부모(인덱스 1)가 비어 있음
        {"kind": "tree", "nodes": [str(i) for i in range(32)]},
        {"kind": "array", "items": []},
        {"kind": "table", "header": ["a", "b"], "rows": [["1"]]},
        {"kind": "graph", "nodes": ["A"]},
    ]
    assert all(validate_figure(f) is None for f in bad)


def test_t26_draw_tree_array_table():
    svg = tree_svg(validate_figure({"kind": "tree", "nodes": ["A", "B", "C", "D"]}))
    assert svg.count("<circle") == 4
    assert svg.count("<line") == 3
    html = figure_html({"kind": "tree", "nodes": ["A", "B"]})
    assert 'src="data:image/svg+xml;base64,' in html and "<svg" not in html
    arr = figure_html({"kind": "array", "items": ["90", "75"], "start": 1})
    assert ">1</td>" in arr and ">2</td>" in arr
    tab = figure_html({"kind": "table", "header": ["<b>"], "rows": [["x"]]})
    assert "&lt;b&gt;" in tab and "<b>" not in tab


def test_t26_tree_text_for_prompts():
    text = figure_text({"kind": "tree", "nodes": ["A", "B", "C"]})
    assert "루트 A" in text and "A의 왼쪽 자식 B" in text


def test_t27_page_reference_triggers_remake(monkeypatch, sample_material):
    prompts_seen = []
    answers = [
        {"question": "p.9 그림의 트리를 중위 순회하시오.", "answer": "D B A C.",
         "rubric": [{"point": "순서", "score": 10}], "source_pages": [9]},
        {"question": "아래 트리를 중위 순회한 결과를 쓰시오.", "answer": "B A C.",
         "rubric": [{"point": "순서", "score": 10}], "source_pages": [9],
         "figure": {"kind": "tree", "nodes": ["A", "B", "C"]}},
    ]

    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        prompts_seen.append(prompt)
        return answers[len(prompts_seen) - 1]

    monkeypatch.setattr(diagnose.llm, "ask_json", fake)
    concept = {"id": "c5", "name": "이진 트리의 순회", "pages": [8, 9, 10]}
    q = diagnose.make_question(concept, ESSAY, sample_material, [1], [])
    assert len(prompts_seen) == 2
    assert "## 다시 만들기" in prompts_seen[1] and "## 다시 만들기" not in prompts_seen[0]
    assert q["question"] == "아래 트리를 중위 순회한 결과를 쓰시오." and q["figure"] is not None


def test_t27_mcq_pointing_twice_becomes_essay(monkeypatch, sample_material):
    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        if "03-C" in prompt.splitlines()[0]:
            return {"question": "위 트리의 전위 순회는?", "choices": ["a", "b", "c", "d"], "answer_index": 0}
        return {"question": "전위 순회의 방문 순서를 쓰시오.", "answer": "루트 먼저다.",
                "rubric": [{"point": "순서", "score": 10}]}

    monkeypatch.setattr(diagnose.llm, "ask_json", fake)
    q = diagnose.make_question({"id": "c5", "name": "순회", "pages": [8]}, MCQ, sample_material, [1], [])
    assert q["kind"] == ESSAY


def test_needs_fix_rules():
    assert needs_fix("15쪽을 보고 답하시오", {"kind": "tree"})
    assert needs_fix("다음 표를 보고 답하시오", None)
    assert not needs_fix("아래 트리를 보고 답하시오", {"kind": "tree", "nodes": ["A"]})
    assert not needs_fix("힙의 삽입 과정을 쓰시오", None)


def test_t28_page_images():
    data = SAMPLE_PDF.read_bytes()
    img = page_jpeg(data, 9)
    assert img is not None and img[:2] == b"\xff\xd8"
    assert page_jpeg(data, 0) is None and page_jpeg(data, 21) is None
    assert page_jpeg(b"PK\x03\x04 pptx", 1) is None


def test_t29_detail_rules():
    assert note.detail_level("지금 당장", 10, "모름") == "자세히"
    assert note.detail_level("복습만", 50, "앎") == "자세히"
    assert note.detail_level("다음", 30, "모름") == "자세히"
    assert note.detail_level("복습만", 15, "모름") == "짧게"
    assert note.detail_level("다음", 45, "진단 안 함") == "보통"
    assert note.detail_level("복습만", 30, "헷갈림") == "보통"
    assert note.detail_level("복습만", 30, "앎") == "짧게"


def test_t29_lecture_order_and_short_has_no_ai(monkeypatch, sample_material):
    concepts = [{"id": "a", "name": "A", "pages": [2, 19]}, {"id": "b", "name": "B", "pages": [10]},
                {"id": "c", "name": "C", "pages": [4, 12]}]
    assert note.lecture_order(concepts, [1, 2, 19]) == ["c", "b", "a"]
    calls = []
    monkeypatch.setattr(note.llm, "ask_json", lambda *a, **k: calls.append(a) or {})
    short = note.make_note({"id": "b", "name": "B", "pages": [10], "summary": "한 줄"}, "짧게",
                           {"exam_pct": 5, "action": "복습만", "status": "진단 안 함"}, None, [], sample_material, [1])
    assert calls == [] and short["summary"] == "한 줄" and short["from_ai"] is False


def test_t29_detailed_prompt_has_diagnosis_and_professor(monkeypatch, sample_material):
    seen = {}

    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        seen["p"] = prompt
        return {"summary": "요약이다(p.15).", "key_points": ["a"] * 9, "pitfalls": ["b"] * 9, "source_pages": [15]}

    monkeypatch.setattr(note.llm, "ask_json", fake)
    utts = [{"concept_id": "c10", "quote": "이건 꼭 알아두세요.", "type": "emphasis", "strength": 3}]
    g = {"score": 3, "error_type": "절차 누락", "reason": "올리는 과정이 빠졌다"}
    n = note.make_note({"id": "c10", "name": "힙의 삽입 연산", "pages": [15, 17]}, "자세히",
                       {"exam_pct": 96, "action": "지금 당장", "status": "모름"}, g, utts, sample_material, [1])
    assert "올리는 과정이 빠졌다" in seen["p"] and "이건 꼭 알아두세요." in seen["p"]
    assert len(n["key_points"]) == 5 and len(n["pitfalls"]) == 2


def _data_with_tree():
    q = {"concept_id": "c5", "name": "순회", "kind": "서술형", "question": "아래 트리를 <중위> 순회하시오.",
         "answer": "B A C.", "rubric": [{"point": "순서", "score": 10}], "source_pages": [9], "pages": [9],
         "figure": {"kind": "tree", "nodes": ["A", "B", "C"]}}
    g = {"score": 2, "status": "모름", "error_type": "절차 누락", "reason": "순서가 틀렸다"}
    e = {"my_gap": "순서를 바꿨다", "explanation": "중위는 LVR이다(p.9).", "check_pages": [9]}
    prio = {"concept_id": "c5", "name": "순회", "exam_pct": 100, "status": "모름", "priority": 100,
            "action": "지금 당장", "rank": 1, "understanding": 0.0}
    return {"priorities": [prio], "questions": {"c5": q}, "grading": {"c5": g}, "explanations": {"c5": e},
            "answers": {"c5": "A B C"}, "concepts": [{"id": "c5", "name": "순회", "pages": [9]}],
            "notes": {"c5": {"detail": "자세히", "summary": "요약(p.9)", "key_points": [], "pitfalls": [],
                             "source_pages": [9]}}, "note_order": ["c5"]}


def test_t30_export_split():
    data = _data_with_tree()
    study, notes = study_html(data), notes_html(data)
    assert study.count("아래 트리를 &lt;중위&gt; 순회하시오.") == 1
    card = study.split("2. 오답노트")[1].split("3. 맞힌 문제")[0]
    assert "A B C" in card and "순서가 틀렸다" in card and "중위는 LVR이다" in card
    assert study.count("data:image/svg+xml;base64,") == 1
    for html in (study, notes):
        assert "image/jpeg" not in html and "#pg-" not in html
    assert "요약(p.9)" not in study and "시험 대비 요약 노트" in notes
    assert "2. 오답노트" not in notes
