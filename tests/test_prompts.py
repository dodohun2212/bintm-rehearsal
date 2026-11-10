# T-12 프롬프트 채우기, T-13 JSON 잘라내기, T-33 잘린 답 다시 받기
import pytest

from core import llm, prompts
from core.concepts import build_prompt


def test_t12_fill(material):
    text = build_prompt({"pages": [{"n": 1, "text": "짧은 자료"}], "n_pages": 1})
    assert "{{MATERIAL}}" not in text and "=== 페이지 1 ===" in text
    for key in prompts.FILES:
        assert prompts.load(key)


def test_t13_extract_json():
    assert llm.extract_json('설명입니다 {"a":1} 끝') == {"a": 1}
    with pytest.raises(llm.BadJSONError):
        llm.extract_json("JSON 없음")


def test_t33_truncated_retry(monkeypatch):
    monkeypatch.delenv("BINTM_FAKE_AI", raising=False)
    calls = []

    def fake_call(prompt, max_tokens, thinking):
        calls.append(max_tokens)
        if len(calls) == 1:
            return '{"a": [1, 2', "max_tokens", 10, 4000
        return '{"a": [1, 2]}', "end_turn", 10, 20

    monkeypatch.setattr(llm, "_call_with_retry", fake_call)
    u = llm.Usage()
    assert llm.ask_json("p", max_tokens=4000, usage=u) == {"a": [1, 2]}
    assert calls == [4000, 8000] and u.calls == 2

    monkeypatch.setattr(llm, "_call_with_retry", lambda p, m, t: ("글만 있음", "end_turn", 1, 1))
    with pytest.raises(llm.BadJSONError) as e:
        llm.ask_json("p")
    assert e.value.code == "E-08"
    monkeypatch.setenv("BINTM_FAKE_AI", "1")
