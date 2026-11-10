"""T-64 녹음 받아쓰기 (가짜 OpenAI)."""
import pytest

from core import stt


class _FakeClient:
    def __init__(self, text=None, fail=False):
        self.text, self.fail = text, fail
        self.sent = None
        outer = self

        class _T:
            def create(self, **kw):
                outer.sent = kw
                if outer.fail:
                    raise RuntimeError("서버 오류")
                return type("R", (), {"text": outer.text})()

        self.audio = type("A", (), {"transcriptions": _T()})()


def test_t64_transcribe(monkeypatch):
    fake = _FakeClient(text=" 오늘은 힙을 배웁니다. ")
    monkeypatch.setattr(stt, "_make_client", lambda key: fake)
    stt.set_api_key("test-key")
    try:
        assert stt.transcribe("a.m4a", b"123") == "오늘은 힙을 배웁니다."
        assert fake.sent["language"] == "ko" and fake.sent["file"] == ("a.m4a", b"123")
        monkeypatch.setattr(stt, "_make_client", lambda key: _FakeClient(fail=True))
        with pytest.raises(stt.STTError) as e:
            stt.transcribe("a.mp3", b"1")
        assert e.value.code == "E-05"
        with pytest.raises(stt.STTError) as e:
            stt.transcribe("a.ogg", b"1")
        assert e.value.code == "E-04"
    finally:
        stt.set_api_key(None)


def test_t64_no_key_is_e05(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    stt.set_api_key(None)
    with pytest.raises(stt.STTError) as e:
        stt.transcribe("a.wav", b"1")
    assert e.value.code == "E-05"
