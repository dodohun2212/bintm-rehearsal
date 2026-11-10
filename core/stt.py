"""F03 녹음 → 대본 (OpenAI 전사 API). STT_MODEL이 None이면 쓰지 않는다."""
from __future__ import annotations

import os

import config


class SttError(Exception):
    """음성 인식 실패 (E-05)."""


def available() -> bool:
    return config.STT_MODEL is not None and bool(os.environ.get("OPENAI_API_KEY", "").strip())


def transcribe(name: str, data: bytes) -> str:
    """녹음 파일을 한국어 대본으로. 파일은 디스크에 쓰지 않고 메모리에서 바로 보낸다."""
    if not available():
        raise SttError("음성 인식 키 없음")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"].strip(), max_retries=2, timeout=600)
        result = client.audio.transcriptions.create(
            model=config.STT_MODEL, file=(name, data), language="ko"
        )
    except Exception as exc:  # 어떤 실패든 E-05로
        raise SttError(f"{type(exc).__name__}") from exc
    text = getattr(result, "text", "") or ""
    if not text.strip():
        raise SttError("빈 대본")
    return text.strip()
