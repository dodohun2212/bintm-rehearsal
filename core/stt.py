"""F03 녹음 → 대본 (OpenAI 전사 API). STT_MODEL이 None이면 끈다."""
from __future__ import annotations

import os

import config

AUDIO_EXTS = ("m4a", "mp3", "wav")

_OPENAI_KEY: str | None = None


class STTError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.code = code


def set_api_key(key: str | None) -> None:
    global _OPENAI_KEY
    _OPENAI_KEY = key or None


def get_api_key() -> str | None:
    return _OPENAI_KEY or os.environ.get("OPENAI_API_KEY") or None


def available() -> bool:
    return bool(config.STT_MODEL) and bool(get_api_key())


def check_audio(name: str, size: int) -> None:
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in AUDIO_EXTS or size > config.MAX_AUDIO_MB * 1024 * 1024:
        raise STTError("E-04", f"{ext} {size}")


def _make_client(key: str):  # 테스트에서 바꿔 끼운다
    from openai import OpenAI

    return OpenAI(api_key=key, timeout=300)


def transcribe(name: str, data: bytes) -> str:
    """녹음을 한국어로 받아쓴다. 파일은 디스크에 쓰지 않고 바이트로 바로 보낸다."""
    check_audio(name, len(data))
    if not config.STT_MODEL:
        raise STTError("E-05", "음성 인식 꺼짐")
    key = get_api_key()
    if not key:
        raise STTError("E-05", "OpenAI 키 없음")
    try:
        client = _make_client(key)
        result = client.audio.transcriptions.create(model=config.STT_MODEL, file=(name, data),
                                                    language="ko")
    except Exception as e:  # noqa: BLE001
        raise STTError("E-05", f"{type(e).__name__}: {e}") from e
    text = getattr(result, "text", None)
    if text is None and isinstance(result, dict):
        text = result.get("text")
    if not text or not str(text).strip():
        raise STTError("E-05", "빈 대본")
    return str(text).strip()
