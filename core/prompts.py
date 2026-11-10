# prompts/*.md 읽기와 {{자리}} 채우기 (BR-10). 버전을 바꿀 때는 아래 파일명 표만 고친다.
import re
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

FILES = {
    "01": "01_개념추출_v1.md",
    "02": "02_강조발화_v1.md",
    "03A": "03A_진단문제_v1.md",
    "03B": "03B_채점_v1.md",
    "03C": "03C_객관식_v1.md",
    "04": "04_보완설명_v1.md",
    "05": "05_요약노트_v1.md",
}


@lru_cache(maxsize=None)
def load(key: str) -> str:
    return (PROMPT_DIR / FILES[key]).read_text(encoding="utf-8")


def fill(key: str, **values) -> str:
    """{{NAME}} 자리를 값으로 바꾼다. 채운 값 안의 {{...}}는 다시 바꾸지 않는다."""
    text = load(key)

    def repl(m):
        name = m.group(1)
        return str(values[name]) if name in values else m.group(0)

    return re.sub(r"\{\{([A-Z_]+)\}\}", repl, text)
