"""prompts/*.md 읽기와 {{자리}} 채우기. 버전 파일명 표는 여기 하나."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# 호출 이름 → 프롬프트 파일 (버전을 바꾸면 이 표만 고친다)
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
    """프롬프트 파일 글을 읽는다(한 번 읽으면 메모리에 둔다)."""
    return (PROMPT_DIR / FILES[name]).read_text(encoding="utf-8")


def slots(name: str) -> set[str]:
    return set(_SLOT.findall(load(name)))


def fill(name: str, **values: str) -> str:
    """{{KEY}} 자리를 채운다. 빠진 자리가 있으면 KeyError."""
    text = load(name)
    need = slots(name)
    missing = need - set(values)
    if missing:
        raise KeyError(f"프롬프트 {name}의 빈 자리: {sorted(missing)}")
    for key in need:
        text = text.replace("{{" + key + "}}", str(values[key]))
    return text
