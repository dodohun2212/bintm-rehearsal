"""T-25~T-30 문제 그림·그림 검사·페이지 그림·요약 노트·내보내기 나누기."""
import base64
import io

from core import llm
from core.diagnose import ESSAY, MCQ, make_question
from core.export import notes_html, study_html
from core.figure import figure_html, figure_text, points_outside, tree_svg, validate_figure
from core.note import detail_level, lecture_order, make_note, short_note
from core.pageimg import render_page
from tests.conftest import SAMPLE_PDF


def test_t25_validate_figure():
    assert validate_figure({"kind": "tree", "nodes": ["A", "B", "C", None, "D"]})["nodes"][4] == "D"
    assert validate_figure({"kind": "array", "items": ["90", "75"], "start": 1})["start"] == 1
    assert validate_figure({"kind": "table", "header": ["a", "b"], "rows": [["1", "2"]]})
    assert validate_figure({"kind": "tree", "nodes": [None, "B"]}) is None  # 루트 없음
    assert validate_figure({"kind": "tree", "nodes": ["A", None, "C", "D"]}) is None  # 부모 없는 노드
    assert validate_figure({"kind": "tree", "nodes": [str(i) for i in range(32)]}) is None
    assert validate_figure({"kind": "array", "items": []}) is None
    assert validate_figure({"kind": "table", "header": ["a", "b"], "rows": [["1"]]}) is None
    assert validate_figure({"kind": "pie"}) is None


def test_t26_draw_figures():
    svg = tree_svg(["A", "B", "C", "D"])
    assert svg.count("<circle") == 4 and svg.count("<line") == 3
    h = figure_html({"kind": "tree", "nodes": ["<b>", "B", "C", "D"]})
    assert "data:image/svg+xml;base64," in h and "<svg" not in h
    b64 = h.split("base64,")[1].split('"')[0]
    assert "&lt;b&gt;" in base64.b64decode(b64).decode("utf-8")
    arr = figure_html({"kind": "array", "items": ["90", "<i>"], "start": 1})
    assert "<td>1</td><td>2</td>" in arr and "&lt;i&gt;" in arr
    assert "[1]=90" in figure_text({"kind": "array", "items": ["90"], "start": 1})


def test_t27_question_pointing_outside_is_remade(monkeypatch):
    assert points_outside("p.9 그림의 트리를 순회하시오", None)
    assert points_outside("오른쪽 트리를 순회하시오", None)
    assert not points_outside("아래 트리를 순회하시오", {"kind": "tree", "nodes": ["A"]})
    prompts_seen = []

    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        prompts_seen.append(prompt)
        if len(prompts_seen) == 1:
            return {"question": "p.9 그림의 트리를 중위 순회하시오.", "answer": "a다.",
                    "rubric": [{"point": "x", "score": 10}], "figure": None}
        return {"question": "아래 트리를 중위 순회하시오.", "answer": "a다.",
                "rubric": [{"point": "x", "score": 10}], "figure": {"kind": "tree", "nodes": ["+", "a", "b"]}}

    monkeypatch.setattr(llm, "ask_json", fake)
    q = make_question({"id": "c5", "name": "순회"}, ESSAY, "글", [9], "(없음)")
    assert "## 다시 만들기" in prompts_seen[1] and q["question"].startswith("아래 트리")

    def always_bad(prompt, max_tokens=4000, thinking=False, usage=None):
        if "프롬프트 03-C" in prompt:
            return {"question": "위 표에서 옳은 것은?", "choices": ["a", "b", "c", "d"], "answer_index": 0}
        return {"question": "서술형이다.", "answer": "답이다.", "rubric": [{"point": "x", "score": 10}]}

    monkeypatch.setattr(llm, "ask_json", always_bad)
    assert make_question({"id": "c5", "name": "순회"}, MCQ, "글", [9], "(없음)")["kind"] == ESSAY


def test_t28_page_image():
    data = SAMPLE_PDF.read_bytes()
    img = render_page(data, 9)
    assert img and img[:2] == b"\xff\xd8"
    assert render_page(data, 0) is None and render_page(data, 21) is None
    from pptx import Presentation
    buf = io.BytesIO()
    Presentation().save(buf)
    assert render_page(buf.getvalue(), 1) is None


def test_t29_detail_rules_and_order(monkeypatch):
    assert detail_level("지금 당장", 30, "모름") == "자세히"
    assert detail_level("복습만", 60, "앎") == "자세히"
    assert detail_level("다음", 40, "모름") == "자세히"
    assert detail_level("다음", 40, "헷갈림") == "보통"
    assert detail_level("다음", 30, "진단 안 함") == "보통"
    assert detail_level("복습만", 30, "헷갈림") == "보통"
    assert detail_level("복습만", 10, "진단 안 함") == "짧게"
    cs = [{"id": "a", "pages": [1, 2]}, {"id": "b", "pages": [9]}, {"id": "c", "pages": [5, 7]}]
    assert lecture_order(cs, [1, 2]) == ["c", "b", "a"]  # 메타 페이지만 있는 개념은 맨 뒤
    calls = []
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: calls.append(a) or {})
    n = short_note({"id": "a", "summary": "한 줄 요약"}, [5])
    assert n["summary"] == "한 줄 요약" and n["from_ai"] is False and not calls
    seen = []

    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        seen.append(prompt)
        return {"summary": "요약이다(p.5). 교수님은 '꼭 알아두세요'라고 했다(녹음).", "key_points": ["k"],
                "pitfalls": [], "source_pages": [5]}

    monkeypatch.setattr(llm, "ask_json", fake)
    utts = [{"concept_id": "a", "quote": "꼭 알아두세요.", "type": "emphasis", "strength": 3}]
    n = make_note({"id": "a", "name": "힙"}, "자세히", {"exam_pct": 90}, {"score": 3, "reason": "삭제와 혼동했다"},
                  utts, "글", [5])
    assert "삭제와 혼동했다" in seen[0] and "꼭 알아두세요." in seen[0]
    assert "(녹음)" in n["summary"]


def _state(fig=None, conf=""):
    q = {"kind": MCQ, "question": "Q<본문>", "choices": ["a", "b", "c", "d"], "answer_index": 0, "answer": "a",
         "explanation": "해설(p.3)", "source_pages": [3], "figure": fig}
    return {"material": {"name": "x.pdf"}, "transcript": None, "concepts": [{"id": "c1", "name": "힙", "pages": [3]}],
            "utterances": [], "meta_pages": [1],
            "scores": {"scores": [{"concept_id": "c1", "name": "힙", "pct": 100, "reasons": []}]},
            "priorities": [{"concept_id": "c1", "name": "힙", "exam_pct": 100, "status": "헷갈림", "understanding": .5,
                            "priority": 50, "action": "지금 당장", "rank": 1}],
            "questions": {"c1": q}, "answers": {}, "dont_know": {}, "mcq_choice": {"c1": 0}, "guessed": {"c1": True},
            "confusion": {"c1": conf}, "grading": {"c1": {"score": 5, "status": "헷갈림", "error_type": "찍어서 맞힘",
                                                          "reason": "찍었다"}},
            "explanations": {"c1": {"my_gap": "놓침", "explanation": "설명이다(p.3).", "check_pages": [3],
                                    "source_pages": [3], "not_found": False, "confusion": conf,
                                    "confusion_reply": "답이다(p.3)." if conf else None}},
            "notes": {"c1": {"concept_id": "c1", "detail": "자세히", "summary": "노트 요약<script>", "key_points": [],
                             "pitfalls": [], "source_pages": [3], "from_ai": True}}}


def test_t30_export_split():
    s = _state(fig={"kind": "tree", "nodes": ["A", "B", "C"]})
    study, notes = study_html(s), notes_html(s)
    assert study.count("Q&lt;본문&gt;") == 1
    assert study.count("data:image/svg+xml") == 1
    assert "image/jpeg" not in study and "#pg-" not in study and "image/jpeg" not in notes
    assert "노트 요약" not in study and "노트 요약&lt;script&gt;" in notes
    card = study.split("2. 오답노트")[1].split("3. 맞힌 문제")[0]
    assert "내가 놓친 점" in card and "찍었다" in card and "Q&lt;본문&gt;" in card
