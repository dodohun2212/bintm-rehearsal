"""prompts/*.md 파일을 읽어 {{자리}}를 채운다. 프롬프트 문장은 코드에 두지 않는다(BR-10)."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# 버전을 바꿀 때는 새 파일을 만들고 이 표만 고친다
FILES = {
    "concepts": "01_개념추출_v1.md",
    "utterances": "02_강조발화_v1.md",
    "essay": "03A_진단문제_v1.md",
    "grade": "03B_채점_v1.md",
    "mcq": "03C_객관식_v1.md",
    "explain": "04_보완설명_v1.md",
    "note": "05_요약노트_v1.md",
}

_SLOT = re.compile(r"\{\{([A-Z_]+)\}\}")


@lru_cache(maxsize=None)
def load(name: str) -> str:
    return (PROMPT_DIR / FILES[name]).read_text(encoding="utf-8")


def slots(name: str) -> set[str]:
    return set(_SLOT.findall(load(name)))


def fill(name: str, **values: str) -> str:
    """{{KEY}} 자리를 values[KEY]로 바꾼다. 채우지 못한 자리가 남으면 오류."""
    text = load(name)
    missing = sorted({k for k in _SLOT.findall(text) if k not in values})
    if missing:
        raise ValueError(f"채우지 않은 자리: {missing}")
    # 한 번에 바꾼다(넣은 글 안의 {{...}}를 다시 바꾸지 않게)
    return _SLOT.sub(lambda m: str(values[m.group(1)]), text)
