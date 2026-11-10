# T-42~T-48, T-50 대본 가리기·형식이 틀린 항목·내가 놓친 점·교재 오류 단정 금지·안내 위치·서술형 크기·프롬프트만 바뀐 배포
import ast
from pathlib import Path

import pytest

from core import prompts, utterances
from core.concepts import NoConceptsError, parse_concepts
from core.explain import fix_gap

ROOT = Path(__file__).resolve().parent.parent
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def test_t42_mask_transcript(monkeypatch):
    seen = {}

    def fake(prompt, **k):
        seen["p"] = prompt
        return {"utterances": [{"concept_id": "c1", "concept_name": "힙", "quote": "학번 [마스킹] 학생 이건 꼭 알아두세요",
                                "type": "emphasis", "strength": 3}]}

    monkeypatch.setattr(utterances, "ask_json", fake)
    tr = "학번 2021136001 학생 이건 꼭 알아두세요. 010-1234-5678 a@b.ac.kr"
    out = utterances.find_utterances([{"id": "c1", "name": "힙"}], tr)
    assert "2021136001" not in seen["p"] and "a@b.ac.kr" not in seen["p"] and "[마스킹]" in seen["p"]
    assert len(out) == 1
    assert "mask(paste_text" in APP
    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    assert "세션 메모리에만" not in APP and "세션 메모리에만" not in readme


def test_t43_bad_items():
    raw = {"concepts": [{"id": None, "name": "힙 삽입", "pages": ["3-4", "p.5", 5.0]},
                        {"id": "c1", "name": "힙 삭제", "pages": [6]}, {"id": "c3", "pages": [1]}, "x",
                        {"id": "c4", "name": "가", "pages": [2]}]}
    out = parse_concepts(raw, 20)
    names = [c["name"] for c in out["concepts"]]
    assert names == ["힙 삽입", "힙 삭제"]
    assert out["concepts"][0]["pages"] == [3, 4, 5] and out["concepts"][0]["id"] not in (None, "c1")
    with pytest.raises(NoConceptsError):
        parse_concepts({"concepts": [{"name": ""}]}, 20)
    us = utterances.parse_utterances({"utterances": [{"concept_id": 1, "quote": "꼭 알아두세요", "type": "emphasis"},
                                                     {"concept_id": "c1", "quote": "꼭", "type": "emphasis"}, "x"]},
                                     "꼭 알아두세요", ["c1"])
    assert len(us) == 1 and us[0]["concept_id"] == "c1"


def test_t44_fix_gap():
    vague = "아직 확인하지 않은 개념이다."
    assert "모르겠어요" in fix_gap(vague, "모름", "'모르겠어요'를 골라 모름으로 표시했어요.")
    assert "아직 확인하지 않은" not in fix_gap(vague, "모름", "답을 비워 두어 모름으로 표시했어요.")
    assert "아직 확인하지 않은" not in fix_gap("", "모름", "삭제와 혼동했다")
    assert fix_gap(vague, "진단 안 함", "") == vague
    assert fix_gap("삭제를 삽입과 혼동했다.", "모름", "x") == "삭제를 삽입과 혼동했다."


def test_t45_no_textbook_error_claims():
    for key in ("03B", "04"):
        assert "강의자료에 오기나 오류가 있다고 쓰지 않습니다" in prompts.load(key)


def test_t46_spinner_fixed():
    i = APP.index('[data-testid="stSpinner"]')
    assert "position:fixed" in APP[i:i + 200] and "bottom" in APP[i:i + 200]


def test_t47_essay_size():
    p = prompts.load("03A")
    assert "최대 2가지" in p and "2~3문장" in p and "2~4개 요소" in p and "2~5" not in p
    assert "2~3문장으로 적어 주세요" in APP


def _needs_reload():
    tree = ast.parse(APP)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "needs_reload")
    ns = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "app.py", "exec"), ns)
    return ns["needs_reload"]


def test_t48_prompt_only_deploy():
    nr = _needs_reload()
    old = {"core/a.py": 1.0, "prompts/01.md": 1.0}
    assert nr(old, {"core/a.py": 1.0, "prompts/01.md": 2.0})
    assert nr(old, {"core/a.py": 1.0, "prompts/01.md": 1.0, "prompts/02.md": 1.0})
    assert nr(None, old)
    assert not nr(old, dict(old))


def test_t50_readme_and_tone():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Yes, get this app back up!" in readme and "AI가 찾은 신호가 같으면" in readme
    assert "~다" in prompts.load("03B")
