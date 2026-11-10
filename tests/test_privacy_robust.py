"""T-41 출제 점수 표기, T-42~T-48 대본 가리기·형식이 틀린 항목·내가 놓친 점·교재 오류·안내 위치·서술형 크기·
프롬프트만 바뀐 배포, T-50 README 안내·채점 말투."""
import ast
import re

import pytest

from core import prompts, utterances
from core.concepts import NoConceptsError, clean_concepts
from core.explain import GENERIC_GAP, fix_gap
from core.export import notes_html, study_html
from core.utterances import clean_utterances
from tests.helpers import ROOT
from tests.test_figure_note import _state

APP = (ROOT / "app.py").read_text(encoding="utf-8")


def _app_func(name):
    tree = ast.parse(APP)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(APP, node)


def test_t41_score_label():
    st = _state()
    st["priorities"][0]["exam_pct"] = 80
    st["scores"][0]["pct"] = 80
    study, notes_doc = study_html(st), notes_html(st)
    assert "80점" in study and "출제 점수 80" in study and "출제 점수 80" in notes_doc
    for doc in (study, notes_doc, APP):
        assert not re.search(r"출제[^<\n]{0,20}\d+\s*%", doc)
    assert "확률이 아니며" in APP


def test_t42_transcript_masked(monkeypatch):
    seen = []
    monkeypatch.setattr(utterances, "ask_json", lambda prompt, **kw: seen.append(prompt) or {
        "utterances": [{"concept_id": "c1", "quote": "이건 꼭 알아두세요.", "type": "emphasis", "strength": 3}]})
    tr = "학번 2021136001입니다. 010-1234-5678로 연락. a@b.ac.kr. 이건 꼭 알아두세요."
    out = utterances.find_utterances(tr, [{"id": "c1", "name": "힙", "summary": "", "keywords": []}])
    assert "[마스킹]" in seen[0] and "2021136001" not in seen[0] and "010-1234-5678" not in seen[0]
    assert len(out) == 1
    assert "mask(paste" in APP
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "세션 메모리에만" not in APP and "세션 메모리에만" not in readme


def test_t43_bad_items_dropped():
    raw = {"concepts": [
        {"id": "c1", "name": "트리", "pages": ["3-4", "p.5"]},
        {"id": None, "name": "힙", "pages": [6.0]},
        {"id": "c3", "name": "", "pages": [1]},
        "x",
    ]}
    out = clean_concepts(raw, 20)["concepts"]
    assert [c["name"] for c in out] == ["트리", "힙"]
    assert out[0]["pages"] == [3, 4, 5] and out[1]["id"] == "c2"
    with pytest.raises(NoConceptsError):
        clean_concepts({"concepts": ["x", {"name": ""}]}, 20)
    u = clean_utterances({"utterances": [{"concept_id": 1, "quote": "꼭", "type": "emphasis", "strength": "3"},
                                          "x", {"quote": None}]}, "꼭 하세요", ["c1"])
    assert len(u) == 1 and u[0]["concept_id"] == "c1"


def test_t44_fix_gap():
    gen = f"{GENERIC_GAP}이다."
    dk = fix_gap(gen, "모름", {"reason": "'모르겠어요'를 골라 모름으로 표시했어요."})
    blank = fix_gap(gen, "모름", {"reason": "답을 비워 두어 모름으로 표시했어요."})
    wrong = fix_gap(gen, "모름", {"reason": "삭제와 삽입을 혼동했다."})
    none = fix_gap("", "진단 안 함", None)
    assert all(GENERIC_GAP not in x for x in (dk, blank, wrong))
    assert "모르겠어요" in dk and "비워" in blank and "혼동" in wrong and "진단" in none
    assert fix_gap("삭제를 삽입과 혼동했다.", "모름", {"reason": "r"}) == "삭제를 삽입과 혼동했다."


def test_t45_no_textbook_error_claim():
    for name in ("grade", "explain"):
        assert "강의자료에 오기나 오류가 있다고 쓰지 않" in prompts.load(name)


def test_t46_spinner_fixed():
    m = re.search(r'\[data-testid="stSpinner"\]\{([^}]*)\}', APP)
    assert m and "position: fixed" in m.group(1) and "bottom" in m.group(1)


def test_t47_essay_size():
    p = prompts.load("essay")
    assert "최대 2가지" in p and "2~3문장" in p and "2~4개 요소" in p
    assert "2~5" not in p
    assert "아는 만큼 2~3문장으로 적어 주세요." in APP


def test_t48_stale_check():
    ns = {}
    exec(_app_func("_changed"), ns)
    changed = ns["_changed"]
    old = {"core/a.py": 1.0, "prompts/p.md": 2.0}
    assert changed(old, {"core/a.py": 1.0, "prompts/p.md": 2.0}, {"prompts/p.md"}) is False
    assert changed(old, {"core/a.py": 1.0, "prompts/p.md": 3.0}, {"prompts/p.md"}) is True
    assert changed({"core/a.py": 1.0}, {"core/a.py": 1.0, "prompts/p.md": 2.0}, {"prompts/p.md"}) is True
    assert changed(old, {"core/a.py": 5.0, "prompts/p.md": 2.0}, {"prompts/p.md"}) is True


def test_t50_readme_and_tone():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Yes, get this app back up!" in readme
    assert "AI가 찾은 신호가 같으면" in readme
    assert "~다" in prompts.load("grade")
