"""prompts/*.md 읽기와 {{자리}} 채우기 (BR-10). 버전은 아래 파일명 표에서 고른다."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

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
def load(key: str) -> str:
    return (PROMPT_DIR / FILES[key]).read_text(encoding="utf-8")


def fill(key: str, **values) -> str:
    """자리를 한 번에 채운다(넣은 글 안의 {{…}}는 다시 바꾸지 않는다)."""
    text = load(key)

    def repl(m):
        name = m.group(1)
        return str(values[name]) if name in values else m.group(0)

    return _SLOT.sub(repl, text)


def pages_text(pages: list[dict]) -> str:
    """페이지마다 `=== 페이지 n ===` 줄을 붙여 한 덩어리로."""
    return "\n".join(f"=== 페이지 {p['n']} ===\n{p['text']}" for p in pages)
