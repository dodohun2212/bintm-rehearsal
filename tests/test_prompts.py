"""T-12, T-13: 프롬프트 채우기, JSON 잘라내기, 잘린 답 다시 받기 준비."""
import pytest

from core import prompts
from core.llm import extract_json


def test_t12_fill_material_leaves_no_slot():
    text = prompts.fill("concepts", MATERIAL="=== 페이지 1 ===\n트리")
    assert "{{MATERIAL}}" not in text
    assert "=== 페이지 1 ===" in text


def test_fill_missing_slot_raises():
    with pytest.raises(ValueError):
        prompts.fill("utterances", TRANSCRIPT="대본")


def test_fill_does_not_expand_slot_inside_value():
    text = prompts.fill("concepts", MATERIAL="자료에 {{MATERIAL}} 글자가 있음")
    assert "자료에 {{MATERIAL}} 글자가 있음" in text


def test_all_prompt_files_load():
    for name in prompts.FILES:
        assert prompts.load(name).startswith("# 프롬프트")


def test_t13_extract_json():
    assert extract_json('설명입니다 {"a":1} 끝') == {"a": 1}


def test_t13_extract_json_rejects_text():
    with pytest.raises(ValueError):
        extract_json("JSON이 없음")
