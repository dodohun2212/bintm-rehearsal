"""F03 녹음 → 대본 (OpenAI 전사 API). STT_MODEL이 None이면 끈다.

파일을 디스크에 쓰지 않고 (이름, 바이트)로 바로 보낸다. 그래서 지울 임시 파일도 없다.
"""
from __future__ import annotations

import config
from core.llm import get_key


def available() -> bool:
    return bool(config.STT_MODEL) and bool(get_key("OPENAI_API_KEY"))


def transcribe(name: str, data: bytes) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=get_key("OPENAI_API_KEY"), timeout=600.0)
    result = client.audio.transcriptions.create(
        model=config.STT_MODEL, file=(name, data), language="ko")
    text = getattr(result, "text", "") or ""
    if not text.strip():
        raise RuntimeError("받아쓴 글이 비어 있음")
    return text
