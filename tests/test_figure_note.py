"""T-25~T-30 문제 그림, 그림 검사, 원본 페이지 그림, 요약 노트, 내보내기 나누기."""
import base64
import io
import re

import pytest

from conftest import SAMPLE_PDF
from core import diagnose as DG
from core import export as EP
from core import note as NT
from core import priority as PR
from core.figure import check_figure, figure_html, tree_svg
from core.pageimg import page_jpeg


# --- T-25 문제 그림 검사 ---
def test_t25_valid_figures_pass():
    assert check_figure({"kind": "tree", "nodes": ["A", "B", "C", None, "D"]}) is not None
    assert check_figure({"kind": "array", "items": ["90", "75", "80"], "start": 1}) is not None
    assert check_figure({"kind": "table", "header": ["연산", "시간 복잡도"], "rows": [["삽입", "O(log n)"]]}) is not None


@pytest.mark.parametrize("fig", [
    {"kind": "tree", "nodes": [None, "A"]},                 # 루트 없음
    {"kind": "tree", "nodes": ["A", None, "C", "D"]},       # 부모 없는 노드(D의 부모 자리가 빔)
    {"kind": "tree", "nodes": [str(i) for i in range(32)]},  # 31칸 초과
    {"kind": "array", "items": [], "start": 0},             # 빈 배열
    {"kind": "table", "header": ["a", "b"], "rows": [["1"]]},  # 열 수가 다른 표
    {"kind": "graph", "nodes": ["A"]},                      # 모르는 종류
    "트리",                                                  # dict가 아님
])
def test_t25_bad_figures_become_none(fig):
    assert check_figure(fig) is None


# --- T-26 문제 그림 그리기 ---
def test_t26_tree_svg_circles_and_lines():
    svg = tree_svg({"kind": "tree", "nodes": ["A", "B", "C", "D"]})
    assert svg.count("<circle") == 4
    assert svg.count("<line") == 3


def test_t26_screen_uses_data_uri_and_escapes():
    fig = check_figure({"kind": "tree", "nodes": ["<x>", "B"]})
    h = figure_html(fig)
    assert "data:image/svg+xml;base64," in h
    assert "<svg" not in h  # st.html이 <svg>를 지우므로 img로
    b64 = re.search(r"base64,([A-Za-z0-9+/=]+)", h).group(1)
    svg = base64.b64decode(b64).decode("utf-8")
    assert "&lt;x&gt;" in svg and "<x>" not in svg


def test_t26_array_index_row_and_table_escape():
    h = figure_html(check_figure({"kind": "array", "items": ["90", "75", "80"], "start": 1}))
    assert "인덱스" in h
    for i in (1, 2, 3):
        assert f"<th>{i}</th>" in h
    t = figure_html(check_figure({"kind": "table", "header": ["연산"], "rows": [["<b>삽입</b>"]]}))
    assert "&lt;b&gt;삽입&lt;/b&gt;" in t and "<b>삽입" not in t


# --- T-27 그림을 가리키는 문제 ---
PAGES = [{"n": 9, "text": "전위 순회는 VLR 순서로 방문한다."}]


def _essay(question, figure=None):
    return {"question": question, "answer": "A B D C 순서다.",
            "rubric": [{"point": "순서", "score": 10}], "source_pages": [9], "figure": figure}


def test_t27_points_away_then_remade(monkeypatch):
    calls = []
    answers = [_essay("p.9 그림의 트리를 전위 순회한 결과를 쓰시오."),
               _essay("아래 트리를 전위 순회한 결과를 쓰시오.", {"kind": "tree", "nodes": ["A", "B", "C", "D"]})]

    def fake(text, max_tokens=None, thinking=False, usage=None):
        calls.append(text)
        return answers[len(calls) - 1]

    monkeypatch.setattr(DG, "ask_json", fake)
    q = DG.make_question("이진 트리의 순회", DG.ESSAY, PAGES, "(없음)")
    assert len(calls) == 2
    assert "## 다시 만들기" not in calls[0]
    assert "## 다시 만들기" in calls[1]
    assert q["question"].startswith("아래 트리")
    assert q["figure"]["kind"] == "tree"


def test_t27_mcq_twice_pointing_falls_back_to_essay(monkeypatch):
    calls = []

    def fake(text, max_tokens=None, thinking=False, usage=None):
        calls.append(text)
        if "프롬프트 03-C" in text[:80]:
            return {"question": "p.9 그림의 트리를 전위 순회한 결과로 옳은 것은?",
                    "choices": ["A B D C", "D B A C", "D B C A", "A B C D"], "answer_index": 0,
                    "explanation": "VLR이다(p.9).", "source_pages": [9], "figure": None}
        return _essay("전위 순회에서 루트를 방문하는 시점과 그 이유를 쓰시오.")

    monkeypatch.setattr(DG, "ask_json", fake)
    q = DG.make_question("이진 트리의 순회", DG.MCQ, PAGES, "(없음)")
    assert q["kind"] == DG.ESSAY
    assert sum(1 for c in calls if "프롬프트 03-C" in c[:80]) == 2
    assert sum(1 for c in calls if "프롬프트 03-A" in c[:80]) == 1


# --- T-28 원본 페이지 그림 ---
def _pptx_bytes():
    from pptx import Presentation
    prs = Presentation()
    prs.slides.add_slide(prs.slide_layouts[5]).shapes.title.text = "슬라이드"
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def test_t28_page_image():
    data = SAMPLE_PDF.read_bytes()
    img = page_jpeg(data, 9)
    assert img is not None and img[:2] == b"\xff\xd8"
    assert page_jpeg(data, 0) is None
    assert page_jpeg(data, 21) is None
    assert page_jpeg(_pptx_bytes(), 1) is None


# --- T-29 요약 노트 ---
@pytest.mark.parametrize("action,pct,status,expected", [
    (PR.NOW, 60, "모름", NT.DETAILED),        # 지금 당장
    (PR.REVIEW, 50, "앎", NT.DETAILED),       # 출제 점수 50 이상
    (PR.NEXT, 30, "모름", NT.DETAILED),       # 진단 모름(20 이상)
    (PR.NEXT, 40, "헷갈림", NT.NORMAL),       # 다음
    (PR.REVIEW, 30, "헷갈림", NT.NORMAL),     # 헷갈림
    (PR.REVIEW, 30, "앎", NT.SHORT),          # 나머지
    (PR.REVIEW, 10, "진단 안 함", NT.SHORT),  # 진단 안 함, 낮은 점수
])
def test_t29_detail_level_rules(action, pct, status, expected):
    assert NT.detail_level(action, pct, status) == expected


def test_t29_lecture_order_meta_only_last():
    concepts = [{"id": "a", "pages": [1, 2]}, {"id": "b", "pages": [5, 3]}, {"id": "c", "pages": [4]}]
    assert NT.lecture_order(concepts, [1, 2]) == ["b", "c", "a"]


def test_t29_short_note_no_ai(monkeypatch):
    calls = []
    monkeypatch.setattr(NT, "ask_json", lambda *a, **k: calls.append(1) or {})
    n = NT.short_note({"id": "c1", "name": "트리 용어", "summary": "한 줄 요약", "pages": [1, 4]}, [1])
    assert calls == []
    assert n["detail"] == NT.SHORT and n["from_ai"] is False and n["summary"] == "한 줄 요약"
    assert n["source_pages"] == [4]


def test_t29_detailed_prompt_has_diagnosis_and_professor(monkeypatch):
    seen = {}

    def fake(text, max_tokens=None, thinking=False, usage=None):
        seen["text"] = text
        return {"summary": "요약이다(p.16).", "key_points": ["k"] * 7, "pitfalls": ["p"] * 3,
                "source_pages": [16, 99]}

    monkeypatch.setattr(NT, "ask_json", fake)
    concept = {"id": "c11", "name": "힙의 삭제 연산", "pages": [16, 17], "objective_quote": "삭제 과정을 설명할 수 있다"}
    info = {"exam_pct": 98, "action": PR.NOW, "status": "모름",
            "grading": {"score": 0, "error_type": "개념 혼동", "reason": "삭제를 삽입 절차와 혼동했다"}}
    utter = [{"concept_id": "c11", "quote": "삭제 과정도 시험에 나옵니다.", "type": "exam_hint", "strength": 3}]
    n = NT.make_note(concept, NT.DETAILED, info, utter, [{"n": 16, "text": "다운힙"}])
    assert "삭제를 삽입 절차와 혼동했다" in seen["text"]
    assert "삭제 과정도 시험에 나옵니다." in seen["text"]
    assert "자세히" in seen["text"]
    assert len(n["key_points"]) == 5 and len(n["pitfalls"]) == 2
    assert n["source_pages"] == [16]


# --- T-30 내보내기 나누기 ---
def _tree_state():
    scores = [{"concept_id": "c5", "name": "이진 트리의 순회", "pct": 100, "raw": 13.0, "body_pages": [8, 9, 10],
               "pages": [8, 9, 10], "reasons": [{"kind": "objective", "points": 3.0, "label": "학습목표"}], "rank": 1}]
    q = {"kind": "서술형", "question": "아래 트리를 전위 순회한 결과를 쓰시오. <script>x</script>",
         "answer": "A B D E C 순서다.", "rubric": [{"point": "순서", "score": 10}], "choices": [],
         "answer_index": None, "explanation": "", "source_pages": [9],
         "figure": {"kind": "tree", "nodes": ["A", "B", "C", "D", "E"], "caption": None}}
    grading = {"c5": {"score": 2, "max": 10, "status": "모름", "error_type": "절차 누락",
                      "reason": "순서가 틀렸다 (p.9).", "rubric_scores": [2]}}
    return dict(
        material={"name": "t.pdf"}, transcript_source=None, scores=scores,
        priorities=PR.compute_priorities(scores, grading), questions={"c5": q}, grading=grading,
        answers={"c5": "A C B"}, dont_know={}, mcq_choice={}, guessed={}, confusion={},
        explanations={"c5": {"concept_id": "c5", "my_gap": "루트 방문 시점을 놓쳤다.",
                             "explanation": "전위 순회는 VLR이다(p.9).", "check_pages": [9], "source_pages": [9],
                             "not_found": False, "not_found_note": None, "confusion_reply": None}},
        notes={"c5": {"concept_id": "c5", "detail": "자세히", "summary": "요약노트전용문장이다(p.8).",
                      "key_points": ["핵심"], "pitfalls": [], "source_pages": [8], "from_ai": True}},
        concepts=[{"id": "c5", "name": "이진 트리의 순회", "pages": [8, 9, 10], "summary": "순회"}],
        utterances=[], meta_pages=[1])


def test_t30_export_split():
    state = _tree_state()
    study, notes = EP.study_html(state, "2026-11-11"), EP.notes_html(state, "2026-11-11")
    assert study.count("아래 트리를 전위 순회한 결과를 쓰시오.") == 1      # 문제는 오답노트에 한 번만
    assert study.count("data:image/svg+xml") == 1                          # 트리 그림 1개
    assert "jpeg" not in study.lower() and "jpeg" not in notes.lower()    # 페이지 그림 없음
    assert "#pg-" not in study and "#pg-" not in notes
    assert "요약노트전용문장이다" not in study and "요약노트전용문장이다" in notes  # 요약 노트는 다른 파일
    assert "&lt;script&gt;" in study and "<script>" not in study          # 이스케이프
    card = study[study.index('class="card"'):study.index('class="foot"')]
    for part in ("아래 트리를", "내 답", "A C B", "<b>채점</b>", "보완 설명", "전위 순회는 VLR이다"):
        assert part in card                                                 # 같은 카드에
