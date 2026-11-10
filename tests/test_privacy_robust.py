"""T-42~T-48 대본 가리기·형식이 틀린 항목·내가 놓친 점·교재 오류 단정 금지·안내 위치·서술형 크기·프롬프트만 바뀐 배포."""
import os
import sys

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from core.concepts import NoConceptError, clean_concepts
from core.explain import fix_gap
from core.extract import MASK, mask
from core.prompts import load
from core.utterances import clean_utterances
from tests.conftest import ROOT


def test_t42_transcript_masked():
    src = (ROOT / "screens" / "s01.py").read_text(encoding="utf-8")
    assert "mask(transcript)" in src  # 대본(붙여넣기·받아쓰기)은 받자마자 가린다
    assert mask("학번: 2021136001 홍길동 학생 질문") == f"학번: {MASK} 홍길동 학생 질문"


def test_t43_bad_items_only_dropped(sample_material):
    raw = {"concepts": [{"id": None, "name": "좋은 개념", "pages": ["3-4", "p.5", 6.0, 99]},
                        {"id": "c2", "name": ""}, "문자열", {"id": "c3", "name": "둘째", "pages": "7"}]}
    res = clean_concepts(raw, sample_material)
    assert [c["name"] for c in res["concepts"]] == ["좋은 개념", "둘째"]
    assert res["concepts"][0]["id"] == "c1" and res["concepts"][0]["pages"] == [3, 4, 5, 6]
    with pytest.raises(NoConceptError):
        clean_concepts({"concepts": [{"name": ""}]}, sample_material)
    utts = clean_utterances({"utterances": [{"concept_id": 5, "quote": "꼭 보세요", "type": "emphasis", "strength": "3"},
                                            {"concept_id": "c5", "quote": "꼭 보세요", "type": "nope"}]},
                            "꼭 보세요", [{"id": "c5", "name": "순회"}])
    assert len(utts) == 1 and utts[0]["concept_id"] == "c5" and utts[0]["strength"] == 3


def test_t44_fix_gap():
    g = {"reason": "삭제를 삽입과 혼동했다.", "error_type": "개념 혼동"}
    assert fix_gap("아직 확인하지 않은 개념이다.", "모름", g) == "진단 문제에서 삭제를 삽입과 혼동했다."
    assert fix_gap("", "모름", {"error_type": "무응답", "reason": "x"}) == "문제가 물은 내용을 아직 답하지 못했다."
    assert fix_gap("놓쳤다.", "헷갈림", g) == "놓쳤다."
    assert fix_gap("", "진단 안 함", None) == "아직 확인하지 않은 개념이다."


def test_t45_no_textbook_error_claim():
    for name in ("grade", "explain"):
        assert "오기나 오류가 있다고 쓰지 않습니다" in load(name)


def test_t46_spinner_fixed_bottom():
    from screens.common import PAGE_CSS
    css = PAGE_CSS.replace(" ", "")
    assert '[data-testid="stSpinner"]{position:fixed;bottom:' in css
    assert "padding-top:4.5rem" in css


def test_t47_essay_size():
    assert "최대 2가지" in load("essay")
    assert "아는 만큼 2~3문장으로 적어 주세요." in (ROOT / "screens" / "s03.py").read_text(encoding="utf-8")


def test_t48_prompt_only_change_reloads_modules():
    st.cache_resource.clear()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.run()
    before = sys.modules["core.prompts"]
    p = ROOT / "prompts" / "05_요약노트_v1.md"
    old = p.stat().st_mtime
    try:
        os.utime(p, (old + 10, old + 10))
        at.run()
        assert sys.modules["core.prompts"] is not before
    finally:
        os.utime(p, (old, old))
        at.run()
