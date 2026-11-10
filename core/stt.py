# F03 녹음 → 대본 (OpenAI 전사 API). STT_MODEL이 None이거나 키가 없으면 쓰지 않는다.
import os
import tempfile

import config


class STTError(Exception):
    code = "E-05"


def available() -> bool:
    return bool(config.STT_MODEL) and bool(os.environ.get("OPENAI_API_KEY"))


def transcribe(data: bytes, filename: str) -> str:
    if not available():
        raise STTError("음성 인식을 쓸 수 없음")
    from openai import OpenAI
    suffix = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ".m4a"
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        with open(path, "rb") as f:
            res = client.audio.transcriptions.create(model=config.STT_MODEL, file=f, language="ko")
        return getattr(res, "text", "") or ""
    except STTError:
        raise
    except Exception as e:
        raise STTError(f"받아쓰기 실패: {type(e).__name__}") from e
    finally:
        # 보낸 직후 임시 파일을 지운다 (BR-06)
        try:
            os.remove(path)
        except OSError:
            pass
