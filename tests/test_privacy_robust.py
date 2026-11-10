"""T-42~T-48, T-50: 대본 가리기, 형식이 틀린 항목, 내가 놓친 점, 교재 오류 단정 금지, 안내 위치, 서술형 크기, 프롬프트만 바뀐 배포."""
import sys

import pytest

from core import prompts, utterances
from core.concepts import NoConceptsError, clean_concepts
from core.explain import fix_gap
from core.diagnose import REASON_BLANK, REASON_DONT_KNOW
from core.utterances import clean_utterances
from tests.conftest import ROOT


def test_t42_transcript_masked_before_ai(monkeypatch):
    seen = {}

    def fake(prompt, max_tokens=4000, thinking=False, usage=None):
        seen["p"] = prompt
        return {"utterances": [{"concept_id": "c1", "concept_name": "a", "quote": "연락은 [마스킹] 로 하세요.",
                                "type": "emphasis", "strength": 2}]}

    monkeypatch.setattr(utterances.llm, "ask_json", fake)
    transcript = "학번 2021136001 학생, 연락은 010-1234-5678 로 하세요. 메일 a@b.ac.kr"
    out = utterances.find_utterances(transcript, [{"id": "c1", "name": "a", "summary": "", "keywords": []}])
    for raw in ("2021136001", "010-1234-5678", "a@b.ac.kr"):
        assert raw not in seen["p"]
    assert "[마스킹]" in seen["p"]
    assert len(out) == 1  # 가린 대본으로 인용 검사가 통과


def test_t42_storage_wording_is_truthful():
    readme = (ROOT / "README.md").read_text(encoding="utf-8") if (ROOT / "README.md").exists() else ""
    common = (ROOT / "screens" / "common.py").read_text(encoding="utf-8")
    assert "세션 메모리에만" not in readme and "세션 메모리에만" not in common
    s01 = (ROOT / "screens" / "s01.py").read_text(encoding="utf-8")
    assert "mask(transcript)" in s01  # 대본을 받자마자 가린다


def test_t43_bad_items_dropped_rest_kept():
    raw = {"meta_pages": ["p.1", 2.0], "concepts": [
        {"id": "c1", "name": "트리", "pages": ["3-4", "p.5"]},
        {"id": None, "name": "힙", "pages": [6]},
        {"id": "c3", "name": "", "pages": [7]},
        "글자",
    ]}
    out = clean_concepts(raw, 20)
    assert [c["name"] for c in out["concepts"]] == ["트리", "힙"]
    assert out["concepts"][0]["pages"] == [3, 4, 5]
    assert out["concepts"][1]["id"] == "c2"
    assert out["meta_pages"] == [1, 2]
    with pytest.raises(NoConceptsError):
        clean_concepts({"concepts": ["x", {"name": ""}]}, 20)


def test_t43_utterance_id_number_becomes_text():
    raw = {"utterances": [{"concept_id": 1, "concept_name": "a", "quote": "꼭 보세요", "type": "emphasis", "strength": 5},
                          {"concept_id": "c1", "quote": "꼭 보세요", "type": "모름", "strength": 1}, "x"]}
    out = clean_utterances(raw, "꼭 보세요", {"c1"})
    assert len(out) == 1 and out[0]["concept_id"] == "c1" and out[0]["strength"] == 3


def test_t44_fix_gap_matches_diagnosis():
    ai = "아직 확인하지 않은 개념이다."
    assert "'모르겠어요'" in fix_gap(ai, "모름", {"reason": REASON_DONT_KNOW})
    assert "비워 두어" in fix_gap(ai, "모름", {"reason": REASON_BLANK})
    assert "부모와 비교" in fix_gap("", "모름", {"reason": "부모와 비교하는 방향이 반대다."})
    assert fix_gap(ai, "진단 안 함", None) == ai
    assert fix_gap("삽입을 삭제와 혼동했다.", "모름", {"reason": "x"}) == "삽입을 삭제와 혼동했다."


def test_t45_prompts_forbid_blaming_material():
    for name in ("grade", "explain"):
        assert "강의자료에 오기나 오류가 있다고 쓰지 않습니다" in prompts.load(name)


def test_t46_spinner_fixed_at_bottom():
    css = (ROOT / "screens" / "common.py").read_text(encoding="utf-8")
    block = css.split('[data-testid="stSpinner"]{', 1)[1].split("}", 1)[0]
    assert "position:fixed" in block and "bottom:" in block


def test_t47_essay_size_rules():
    text = prompts.load("essay")
    assert "최대 2가지" in text and "2~3문장" in text and "2~4개 요소" in text
    assert "2~5" not in text
    s03 = (ROOT / "screens" / "s03.py").read_text(encoding="utf-8")
    assert "아는 만큼 2~3문장으로 적어 주세요." in s03


def _load_app_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("app_under_test", ROOT / "app.py")
    source = (ROOT / "app.py").read_text(encoding="utf-8").split("_drop_stale_modules()\n\nimport streamlit")[0]
    module = type(sys)("app_under_test")
    module.__file__ = str(ROOT / "app.py")
    exec(compile(source, str(ROOT / "app.py"), "exec"), module.__dict__)
    return module


def test_t48_prompt_change_drops_modules(monkeypatch):
    app = _load_app_module()
    import core.score  # noqa: F401

    monkeypatch.delattr(sys, "_bintm_mtimes", raising=False)
    assert app._drop_stale_modules() is True  # 프롬프트가 기록에 없으면 바뀐 것으로 본다
    import core.score  # noqa: F401,F811

    assert app._drop_stale_modules() is False  # 그대로면 아무것도 안 함
    assert "core.score" in sys.modules
    some_prompt = next(k for k in sys._bintm_mtimes if k.endswith(".md"))
    sys._bintm_mtimes[some_prompt] = 0.0
    assert app._drop_stale_modules() is True
    assert "core.score" not in sys.modules
    import core.score  # noqa: F401,F811  다시 읽기


def test_t50_grading_prompt_tone():
    assert '"~다"' in prompts.load("grade")


def test_t50_readme_wake_and_wording():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Yes, get this app back up!" in readme
    assert "AI가 찾은 신호가 같으면" in readme
    assert "출제를 보장하지 않습니다" in readme
    assert "개념마다 보완 설명" not in readme
    assert len(readme.splitlines()) <= 250
