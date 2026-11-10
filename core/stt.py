"""F03 녹음 → 대본 (OpenAI 전사 API). STT_MODEL이 None이거나 키가 없으면 쓰지 않는다."""
from __future__ import annotations

import os
import tempfile

import config


class STTError(Exception):
    code = "E-05"
    user_message = "녹음을 글자로 바꾸지 못해 녹음 없이 계산했어요. 대본 붙여넣기로 다시 분석할 수 있어요"


def available() -> bool:
    return bool(config.STT_MODEL) and bool(os.environ.get("OPENAI_API_KEY"))


def transcribe(name: str, data: bytes) -> str:
    """녹음을 한국어 글로 받아쓴다. 임시 파일은 보낸 직후 지운다(BR-06)."""
    if not available():
        raise STTError("음성 인식 키 없음")
    from openai import OpenAI

    suffix = "." + name.rsplit(".", 1)[-1].lower()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        tmp.write(data)
        tmp.close()
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        with open(tmp.name, "rb") as f:
            res = client.audio.transcriptions.create(model=config.STT_MODEL, file=f, language="ko")
        return getattr(res, "text", "") or ""
    except Exception as e:
        raise STTError(f"{type(e).__name__}: {e}") from e
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
