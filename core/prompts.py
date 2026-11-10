"""prompts/*.md 읽기와 {{자리}} 채우기 (BR-10). 버전을 바꿀 때는 아래 표의 파일명만 고친다."""
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
def load(name: str) -> str:
    return (PROMPT_DIR / FILES[name]).read_text(encoding="utf-8")


def fill(name: str, **values) -> str:
    """한 번에 치환한다(넣은 글 안의 {{…}}는 다시 바꾸지 않는다)."""
    text = load(name)
    return _SLOT.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


def pages_block(pages: list[dict]) -> str:
    """[{n, text}] → '=== 페이지 n ===' 줄을 붙인 한 덩어리."""
    return "\n\n".join(f"=== 페이지 {p['n']} ===\n{p['text']}" for p in pages)
