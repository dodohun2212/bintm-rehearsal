"""T-12, T-13 프롬프트 채우기와 JSON 잘라내기."""
import pytest

from core import llm, prompts


def test_t12_fill_material():
    text = prompts.fill("concepts", MATERIAL="=== 페이지 1 ===\n짧은 자료")
    assert "{{MATERIAL}}" not in text and "짧은 자료" in text


def test_all_prompt_files_have_slots_and_fill():
    for name in prompts.FILES:
        need = prompts.slots(name)
        assert need, name
        text = prompts.fill(name, **{k: "값" for k in need})
        assert "{{" not in text


def test_missing_slot_is_error():
    with pytest.raises(KeyError):
        prompts.fill("concepts")


def test_t13_cut_json():
    assert llm.cut_json('설명입니다 {"a":1} 끝') == {"a": 1}
    with pytest.raises(ValueError):
        llm.cut_json("JSON 없음")
