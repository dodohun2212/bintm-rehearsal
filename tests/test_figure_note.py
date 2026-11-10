# T-25~T-30 문제 그림·그림 검사·페이지 그림·요약 노트·내보내기, T-41 출제 점수 표기
import base64
import re
from pathlib import Path

from core import diagnose, export, note
from core.diagnose import ESSAY, MCQ
from core.figure import figure_html, refers_elsewhere, tree_svg, validate_figure
from core.pageimg import page_jpeg

ROOT = Path(__file__).resolve().parent.parent


def test_t25_validate_figure():
    assert validate_figure({"kind": "tree", "nodes": ["A", "B", "C", None, "D"]})
    assert validate_figure({"kind": "array", "items": ["90", "75"], "start": 1})
    assert validate_figure({"kind": "table", "header": ["a", "b"], "rows": [["1", "2"]]})
    bad = [{"kind": "tree", "nodes": [None, "B"]}, {"kind": "tree", "nodes": ["A", None, "C", "D"]},
           {"kind": "tree", "nodes": [str(i) for i in range(32)]}, {"kind": "array", "items": []},
           {"kind": "table", "header": ["a", "b"], "rows": [["1"]]}, {"kind": "graph"}]
    assert all(validate_figure(b) is None for b in bad)


def test_t26_draw_figure():
    fig = {"kind": "tree", "nodes": ["A", "B", "C", "<D>"]}
    svg = tree_svg(validate_figure(fig))
    assert svg.count("<circle") == 4 and svg.count("<line") == 3 and "&lt;D&gt;" in svg
    h = figure_html(fig)
    assert "data:image/svg+xml;base64," in h and "<svg" not in h
    arr = figure_html({"kind": "array", "items": ["90", "<b>"], "start": 1})
    assert ">1<" in arr and ">2<" in arr and "&lt;b&gt;" in arr
    tbl = figure_html({"kind": "table", "header": ["연산"], "rows": [["삽입"]]})
    assert "<table" in tbl and "삽입" in tbl


def test_t27_refers_and_retry(monkeypatch, material, analysis):
    assert refers_elsewhere("p.9 그림의 트리를 중위 순회하시오", None)
    assert refers_elsewhere("오른쪽 트리를 순회하시오", None)
    assert not refers_elsewhere("아래 트리를 순회하시오", {"kind": "tree"})
    c = analysis["concepts"][4]
    fig = {"kind": "tree", "nodes": ["A", "B", "C"]}
    rub = [{"point": "결과", "score": 10}]
    seq = iter([{"question": "p.9 그림의 트리를 중위 순회한 결과를 쓰시오.", "answer": "B A C이다.", "rubric": rub},
                {"question": "아래 트리를 중위 순회한 결과를 쓰시오.", "answer": "B A C이다.", "rubric": rub, "figure": fig}])
    prompts_seen = []

    def fake(prompt, **k):
        prompts_seen.append(prompt)
        return next(seq)

    monkeypatch.setattr(diagnose, "ask_json", fake)
    q = diagnose.make_question(c, ESSAY, material, analysis["meta"], "(없음)")
    assert q["figure"] and "## 다시 만들기" in prompts_seen[1]
    mcq_bad = {"question": "p.9 그림의 트리 순회 결과로 옳은 것은?", "choices": ["가", "나", "다", "라"], "answer_index": 0}
    seq2 = iter([mcq_bad, mcq_bad, {"question": "순회 결과를 쓰고 이유를 쓰시오.", "answer": "답이다.", "rubric": rub}])
    monkeypatch.setattr(diagnose, "ask_json", lambda *a, **k: next(seq2))
    q = diagnose.make_question(c, MCQ, material, analysis["meta"], "(없음)")
    assert q["kind"] == ESSAY


def test_t28_page_image():
    data = (ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf").read_bytes()
    img = page_jpeg(data, 9)
    assert img and img[:2] == b"\xff\xd8"
    assert page_jpeg(data, 0) is None and page_jpeg(data, 21) is None
    assert page_jpeg(b"PK\x03\x04 not a pdf", 1) is None


def test_t29_note_rules(analysis, material):
    assert note.detail_level("지금 당장", 30, "모름") == "자세히"
    assert note.detail_level("복습만", 50, "앎") == "자세히"
    assert note.detail_level("다음", 25, "모름") == "자세히"
    assert note.detail_level("다음", 40, "진단 안 함") == "보통"
    assert note.detail_level("복습만", 30, "헷갈림") == "보통"
    assert note.detail_level("복습만", 10, "모름") == "짧게"
    assert note.detail_level("복습만", 45, "앎") == "짧게"
    cs = [{"id": "a", "pages": [1, 2]}, {"id": "b", "pages": [9]}, {"id": "c", "pages": [5, 12]}]
    assert note.lecture_order(cs, [1, 2]) == ["c", "b", "a"]
    from core.llm import Usage
    c = analysis["concepts"][9]
    u = Usage()
    short = note.short_note(c, analysis["meta"])
    assert short["detail"] == "짧게" and not short["from_ai"] and u.calls == 0
    pr = {"exam_pct": 96, "action": "지금 당장", "status": "모름"}
    g = {"score": 2, "error_type": "개념 혼동", "reason": "삭제와 혼동했다"}
    info = note.concept_info(c, "자세히", pr, analysis["utts"], g)
    p = note.build_prompt(c, "자세히", info, "=== 페이지 15 ===\n글")
    assert "삭제와 혼동했다" in p and any(u["quote"][:10] in p for u in analysis["utts"] if u["concept_id"] == c["id"])
    n = note.make_note({"concept": c, "detail": "보통", "pr": pr, "g": g, "utterances": []}, material, analysis["meta"], u)
    assert n["from_ai"] and u.calls == 1


def _state(tree=True):
    q = {"kind": ESSAY, "question": "아래 트리를 <순회>하시오", "answer": "B A C이다.",
         "rubric": [{"point": "결과", "score": 10}], "source_pages": [9],
         "figure": {"kind": "tree", "nodes": ["A", "B", "C"]} if tree else None}
    return {
        "material": {"name": "s.pdf"}, "transcript_source": "paste", "date": "2026-11-11",
        "scores": [{"concept_id": "c1", "name": "순회", "pct": 80, "reasons": [{"label": "학습목표", "points": 3}]}],
        "priorities": [{"concept_id": "c1", "name": "순회", "exam_pct": 80, "status": "모름", "understanding": 0,
                        "priority": 80, "action": "지금 당장", "rank": 1}],
        "questions": {"c1": q}, "grading": {"c1": {"score": 2, "status": "모름", "error_type": "기타",
                                                  "reason": "틀렸다 (p.9)", "rubric_scores": [2]}},
        "answers": {"c1": "모름<script>"}, "dont_know": {}, "mcq_choice": {}, "guessed": {}, "confusion": {},
        "explanations": {"c1": {"my_gap": "놓쳤다", "explanation": "설명이다 (p.9).", "check_pages": [9],
                                "source_pages": [9], "not_found": True, "not_found_note": "없음",
                                "confusion_reply": None}},
        "notes": {"c1": {"concept_id": "c1", "detail": "자세히", "summary": "요약 <b>", "key_points": ["k"],
                         "pitfalls": [], "source_pages": [9], "from_ai": True}},
        "concepts": [{"id": "c1", "name": "순회", "pages": [9]}], "meta_pages": [], "utterances": [],
    }


def test_t30_export_split():
    s = _state()
    study, notes_doc = export.study_html(s), export.notes_html(s)
    assert study.count("아래 트리를 &lt;순회&gt;하시오") == 1
    card = study.split("2. 오답노트")[1]
    assert "모름&lt;script&gt;" in card and "놓쳤다" in card and "설명이다" in card
    assert study.count("data:image/svg+xml") == 1
    for doc in (study, notes_doc):
        assert "image/jpeg" not in doc and "#pg-" not in doc and "<script>" not in doc
    assert "요약 &lt;b&gt;" in notes_doc and "요약 &lt;b&gt;" not in study
    assert "올린 자료에서 찾지 못함" in study and "E-12" not in study


def test_t41_score_wording():
    s = _state()
    study, notes_doc = export.study_html(s), export.notes_html(s)
    assert "출제 가능성 점수 80점" in study and "출제 점수 80" in study and "출제 점수 80" in notes_doc
    for doc in (study, notes_doc):
        assert not re.search(r"출제[^<]{0,20}%", doc)
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "확률이 아니며" in app and not re.search(r"출제[^\n\"]{0,20}%", app)
