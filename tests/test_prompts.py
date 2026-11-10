"""T-12 프롬프트 채우기, T-13 JSON 잘라내기, BR-10 프롬프트 파일."""
from core import prompts
from core.llm import extract_json


def test_t12_fill_material():
    text = prompts.fill("concepts", MATERIAL=prompts.pages_block([{"n": 1, "text": "트리"}]))
    assert "{{MATERIAL}}" not in text
    assert "=== 페이지 1 ===" in text


def test_fill_does_not_resubstitute():
    text = prompts.fill("essay", CONCEPT_NAME="{{PAGES}}", OTHER_CONCEPTS="(없음)", PAGES="본문")
    assert '"{{PAGES}}"' in text  # 넣은 글 안의 자리는 다시 바꾸지 않는다


def test_all_prompt_files_exist():
    for name in prompts.FILES:
        assert len(prompts.load(name)) > 100


def test_t13_extract_json():
    assert extract_json('설명입니다 {"a":1} 끝') == {"a": 1}
