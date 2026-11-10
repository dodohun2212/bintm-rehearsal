"""T-41~T-48 출제 점수 표기, 대본 가리기, 형식이 틀린 항목, 내가 놓친 점, 교재 오류 단정 금지,
기다리는 안내 위치, 서술형 크기, 프롬프트만 바뀐 배포."""
import ast
import re

import pytest

from conftest import ROOT
from core import concepts as CC
from core import export as EP
from core import priority as PR
from core import utterances as UT
from core.diagnose import REASON_DONT_KNOW, REASON_EMPTY
from core.explain import fix_gap

APP = (ROOT / "app.py").read_text(encoding="utf-8")
PROMPTS = ROOT / "prompts"


# --- T-41 출제 점수 표기 ---
def test_t41_score_not_percent():
    scores = [{"concept_id": "c1", "name": "힙의 삽입 연산", "pct": 80, "raw": 10.0, "body_pages": [15],
               "pages": [15], "reasons": [], "rank": 1}]
    grading = {"c1": {"score": 0, "max": 10, "status": "모름", "error_type": "무응답", "reason": "r", "rubric_scores": None}}
    q = {"kind": "서술형", "question": "삽입 절차를 쓰시오.", "answer": "끝에 넣는다.", "rubric": [{"point": "a", "score": 10}],
         "choices": [], "answer_index": None, "explanation": "", "source_pages": [15], "figure": None}
    state = dict(material={"name": "t.pdf"}, scores=scores, priorities=PR.compute_priorities(scores, grading),
                 questions={"c1": q}, grading=grading, answers={}, dont_know={"c1": True}, mcq_choice={}, guessed={},
                 confusion={}, explanations={},
                 notes={"c1": {"concept_id": "c1", "detail": "자세히", "summary": "요약(p.15).", "key_points": [],
                               "pitfalls": [], "source_pages": [15], "from_ai": True}},
                 concepts=[{"id": "c1", "name": "힙의 삽입 연산", "pages": [15]}], utterances=[], meta_pages=[])
    study, notes = EP.study_html(state), EP.notes_html(state)
    assert "출제 가능성 점수 80점" in study
    assert "출제 점수 80" in study and "출제 점수 80" in notes
    for h in (study, notes):
        assert not re.search(r"출제[^<]{0,20}%", h)
    assert "확률이 아니며" in APP


# --- T-42 대본 가리기 ---
TRANSCRIPT = "학번 2021136001 학생, 연락처 010-1234-5678, 메일 a@b.ac.kr 입니다. 이건 꼭 알아두세요."


def test_t42_transcript_masked_before_ai(monkeypatch):
    seen = {}

    def fake(text, max_tokens=None, thinking=False, usage=None):
        seen["text"] = text
        return {"utterances": [{"concept_id": "c1", "concept_name": "힙", "quote": "이건 꼭 알아두세요.",
                                "type": "emphasis", "strength": 3},
                               {"concept_id": "c1", "concept_name": "힙", "quote": "연락처 [마스킹], 메일",
                                "type": "emphasis", "strength": 1}]}

    monkeypatch.setattr(UT, "ask_json", fake)
    out = UT.find_utterances(TRANSCRIPT, [{"id": "c1", "name": "힙", "summary": "", "keywords": []}])
    for raw in ("2021136001", "010-1234-5678", "a@b.ac.kr"):
        assert raw not in seen["text"]
    assert "[마스킹]" in seen["text"]
    assert len(out) == 2   # 가린 대본으로 인용 검사가 통과


def test_t42_app_masks_on_receipt_and_honest_wording():
    assert "XT.mask(paste)" in APP
    assert "세션 메모리에만" not in APP
    readme = ROOT / "README.md"
    if readme.exists():
        assert "세션 메모리에만" not in readme.read_text(encoding="utf-8")


# --- T-43 형식이 틀린 AI 항목 ---
def test_t43_bad_concepts_dropped_only():
    raw = {"concepts": [
        {"id": "c1", "name": "힙의 삽입", "pages": [15]},
        {"id": None, "name": "힙의 삭제", "pages": "p.5"},
        {"id": "c3", "name": "", "pages": [3]},           # 이름 없음
        "글자 하나뿐인 항목",                              # dict가 아님
        {"id": "c5", "name": "트리 순회", "pages": ["3-4", 25]},
    ]}
    out = CC.clean_concepts(raw, n_pages=20)
    names = [c["name"] for c in out["concepts"]]
    assert names == ["힙의 삽입", "힙의 삭제", "트리 순회"]
    by = {c["name"]: c for c in out["concepts"]}
    assert by["힙의 삭제"]["id"] == "c2"
    assert by["힙의 삭제"]["pages"] == [5]
    assert by["트리 순회"]["pages"] == [3, 4]   # 범위 밖 25는 버림


def test_t43_no_usable_concept_is_e09():
    with pytest.raises(CC.NoConceptsError):
        CC.clean_concepts({"concepts": [{"name": None}, "x", {"id": "c1"}]}, n_pages=20)


def test_t43_bad_utterances_dropped_only():
    transcript = "이건 꼭 알아두세요. 다음 주에 다시 봅니다."
    raw = {"utterances": [
        {"concept_id": 5, "concept_name": "a", "quote": "이건 꼭 알아두세요.", "type": "emphasis", "strength": 5},
        {"concept_id": "c99", "concept_name": "b", "quote": "다음 주에 다시 봅니다.", "type": "deferral", "strength": "2"},
        {"concept_id": "c5", "concept_name": "c", "quote": "이건 꼭 알아두세요.", "type": "foo", "strength": 2},
        {"concept_id": "c5", "concept_name": "d", "quote": "대본에 없는 말", "type": "emphasis", "strength": 2},
        "글자",
    ]}
    out = UT.clean_utterances(raw, transcript, {"c5"})
    assert len(out) == 2
    assert out[0]["concept_id"] == "c5" and out[0]["strength"] == 3
    assert out[1]["concept_id"] is None and out[1]["strength"] == 2


# --- T-44 내가 놓친 점 ---
VAGUE = "아직 확인하지 않은 개념이다."


def test_t44_fix_gap_matches_diagnosis():
    g = fix_gap(VAGUE, "모름", {"reason": REASON_DONT_KNOW})
    assert "아직 확인하지 않은" not in g and "모르겠어요" in g
    g = fix_gap(VAGUE, "모름", {"reason": REASON_EMPTY})
    assert "아직 확인하지 않은" not in g and "비워" in g
    wrong = "고른 보기가 정답이 아니에요. 정답: 큰 자식"
    g = fix_gap(VAGUE, "모름", {"reason": wrong, "error_type": "오답"})
    assert "아직 확인하지 않은" not in g and wrong in g
    g = fix_gap("", "헷갈림", {"reason": "이유"})
    assert g and "아직 확인하지 않은" not in g


def test_t44_not_diagnosed_and_specific_kept():
    assert fix_gap(VAGUE, "진단 안 함", None) == VAGUE
    assert fix_gap("", "진단 안 함", None) == VAGUE
    specific = "삭제를 삽입 절차(위로 올리기)와 혼동했다."
    assert fix_gap(specific, "모름", {"reason": "r"}) == specific


# --- T-45 교재 오류 단정 금지 ---
@pytest.mark.parametrize("name", ["03B_채점_v1.md", "04_보완설명_v1.md"])
def test_t45_no_textbook_error_claims(name):
    assert "강의자료에 오기나 오류가 있다고 쓰지 않습니다" in (PROMPTS / name).read_text(encoding="utf-8")


# --- T-46 기다리는 안내 위치 ---
def test_t46_spinner_fixed_bottom():
    m = re.search(r'\[data-testid="stSpinner"\]\{([^}]*)\}', APP)
    assert m and re.search(r"position:\s*fixed", m.group(1)) and "bottom" in m.group(1)


# --- T-47 서술형 크기 ---
def test_t47_essay_size():
    p = (PROMPTS / "03A_진단문제_v1.md").read_text(encoding="utf-8")
    for s in ("최대 2가지", "2~3문장", "2~4개 요소"):
        assert s in p
    assert "2~5" not in p
    assert "2~3문장" in APP


# --- T-48 프롬프트만 바뀐 배포 ---
def _is_stale():
    tree = ast.parse(APP)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_is_stale")
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "app_is_stale", "exec"), ns)
    return ns["_is_stale"]


def test_t48_stale_check():
    f = _is_stale()
    old = {"p/01.md": 1.0, "core/a.py": 1.0}
    assert f(old, dict(old)) is False                                   # 그대로면 아무것도 안 함
    assert f(old, {"p/01.md": 2.0, "core/a.py": 1.0}) is True           # 프롬프트 시각이 바뀜
    assert f({"core/a.py": 1.0}, {"p/01.md": 1.0, "core/a.py": 1.0}) is True  # 프롬프트가 기록에 없음
    assert f(None, {"p/01.md": 1.0}) is True                            # 첫 기록에서도 새로 읽게
    assert f(old, {"p/01.md": 1.0, "core/a.py": 2.0}) is True           # 모듈 시각이 바뀜
