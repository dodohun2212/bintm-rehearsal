"""T-12, T-13: 프롬프트 채우기와 JSON 잘라내기."""
import pytest

from core import prompts
from core.llm import parse_json


def test_t12_fill_material():
    text = prompts.fill("concepts", MATERIAL=prompts.pages_text([{"n": 1, "text": "힙 {{X}}"}]))
    assert "{{MATERIAL}}" not in text
    assert "=== 페이지 1 ===" in text and "힙 {{X}}" in text  # 넣은 글 안의 자리는 다시 바꾸지 않는다


def test_all_prompt_files_load():
    for key in prompts.FILES:
        assert prompts.load(key).startswith("# 프롬프트")


def test_t13_json_cut():
    assert parse_json('설명입니다 {"a":1} 끝') == {"a": 1}
    with pytest.raises(ValueError):
        parse_json("JSON 없음")
