"""언어 모델 호출을 하나로 모은 곳. 모든 호출은 ask_json()을 거친다."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field

import config
from core import fake_ai

# 모든 호출에 붙는 시스템 지시 한 줄 (BR-10 예외 1)
SYSTEM_PROMPT = "당신은 JSON만 출력합니다. JSON 앞뒤에 설명 문장이나 코드 블록 표시를 붙이지 않습니다."

MAX_TOKENS_CEILING = 16000
RETRY_WAITS = (2, 4)  # 네트워크·429·5xx 재시도 대기(초)

_API_KEY: str | None = None
_KEY_LOCK = threading.Lock()


class AIError(Exception):
    """AI 호출 실패. code는 화면 에러 번호(E-06/E-07/E-08)."""

    code = "E-07"
    message = "AI 서버와 연결이 어려워요. 잠시 후 다시 시도 버튼을 눌러 주세요."


class KeyMissingError(AIError):
    code = "E-06"
    message = "AI 키가 설정되지 않았어요. README의 설정 방법을 보세요."


class ConnectionFailError(AIError):
    code = "E-07"
    message = "AI 서버와 연결이 어려워요. 잠시 후 다시 시도 버튼을 눌러 주세요."


class BadJSONError(AIError):
    code = "E-08"
    message = "AI 답을 읽지 못했어요. 다시 시도해 주세요."


@dataclass
class Usage:
    """AI 호출 수·토큰·시간. 스레드마다 따로 만들고 메인 스레드에서 merge한다."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0
    stages: dict = field(default_factory=dict)  # 단계 이름 → 걸린 시간(초), 같은 단계는 더한다

    def add_call(self, in_tok: int, out_tok: int, secs: float) -> None:
        self.calls += 1
        self.input_tokens += int(in_tok or 0)
        self.output_tokens += int(out_tok or 0)
        self.seconds += float(secs or 0)

    def merge(self, other: "Usage") -> None:
        """다른 묶음을 더한다. 호출 수도 묶음 안의 호출 수만큼 늘린다."""
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.seconds += other.seconds
        for k, v in other.stages.items():
            self.stages[k] = self.stages.get(k, 0.0) + v

    def add_stage(self, name: str, secs: float) -> None:
        self.stages[name] = self.stages.get(name, 0.0) + float(secs)

    def to_dict(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.input_tokens,
                "output_tokens": self.output_tokens, "seconds": round(self.seconds, 1),
                "stages": {k: round(v, 1) for k, v in self.stages.items()}}

    @classmethod
    def from_dict(cls, d: dict | None) -> "Usage":
        d = d or {}
        return cls(calls=int(d.get("calls", 0)), input_tokens=int(d.get("input_tokens", 0)),
                   output_tokens=int(d.get("output_tokens", 0)), seconds=float(d.get("seconds", 0)),
                   stages=dict(d.get("stages", {})))


def set_api_key(key: str | None) -> None:
    """화면(app.py)이 st.secrets에서 읽은 키를 넘긴다. core는 streamlit을 모른다."""
    global _API_KEY
    with _KEY_LOCK:
        _API_KEY = key or None


def get_api_key() -> str | None:
    """st.secrets(set_api_key로 받은 값) → 환경변수 순."""
    return _API_KEY or os.environ.get("ANTHROPIC_API_KEY") or None


def has_key() -> bool:
    return fake_ai.enabled() or bool(get_api_key())


def cut_json(text: str) -> dict:
    """첫 '{'부터 마지막 '}'까지만 잘라 파싱한다. 실패하면 ValueError."""
    if not isinstance(text, str):
        raise ValueError("글이 아님")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON 괄호가 없음")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아님")
    return data


def _call_model(prompt_text: str, max_tokens: int, thinking: bool) -> tuple[str, str, int, int]:
    """모델을 한 번 부른다. (글, stop_reason, 입력 토큰, 출력 토큰). 테스트에서 바꿔 끼운다."""
    import anthropic

    key = get_api_key()
    if not key:
        raise KeyMissingError("키 없음")
    client = anthropic.Anthropic(api_key=key, timeout=config.LLM_TIMEOUT_SEC, max_retries=0)
    kwargs = dict(model=config.LLM_MODEL, max_tokens=max_tokens, system=SYSTEM_PROMPT,
                  messages=[{"role": "user", "content": prompt_text}])
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    try:
        with client.messages.stream(**kwargs) as stream:
            msg = stream.get_final_message()
    except anthropic.BadRequestError as e:
        # 생각 모드를 받지 않는 모델이면 생각 모드 없이 한 번 더
        if thinking and "thinking" in str(e).lower():
            return _call_model(prompt_text, max_tokens, False)
        raise
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    usage = getattr(msg, "usage", None)
    return (text, str(getattr(msg, "stop_reason", "") or ""),
            int(getattr(usage, "input_tokens", 0) or 0), int(getattr(usage, "output_tokens", 0) or 0))


def _is_retryable(e: Exception) -> bool:
    try:
        import anthropic
    except Exception:  # pragma: no cover
        return False
    if isinstance(e, (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError,
                      anthropic.InternalServerError)):
        return True
    status = getattr(e, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def _is_auth_error(e: Exception) -> bool:
    try:
        import anthropic
    except Exception:  # pragma: no cover
        return False
    return isinstance(e, (anthropic.AuthenticationError, anthropic.PermissionDeniedError))


def _call_with_retry(prompt_text: str, max_tokens: int, thinking: bool, usage: Usage | None):
    """네트워크·429·5xx는 2초→4초 기다리고 최대 2회 더."""
    last: Exception | None = None
    for attempt in range(len(RETRY_WAITS) + 1):
        t0 = time.time()
        try:
            text, stop, in_tok, out_tok = _call_model(prompt_text, max_tokens, thinking)
            if usage is not None:
                usage.add_call(in_tok, out_tok, time.time() - t0)
            return text, stop
        except AIError:
            raise
        except Exception as e:  # noqa: BLE001
            if _is_auth_error(e):
                raise KeyMissingError(str(e)) from e
            last = e
            if not _is_retryable(e) or attempt >= len(RETRY_WAITS):
                break
            time.sleep(RETRY_WAITS[attempt])
    raise ConnectionFailError(f"{type(last).__name__}: {last}") from last


def ask_json(prompt_text: str, max_tokens: int = config.AI_MAX_TOKENS, thinking: bool = False,
             usage: Usage | None = None) -> dict:
    """프롬프트를 보내 JSON(dict)을 받는다. 파싱 실패는 1회 더, 잘리면 상한을 두 배로 1회 더."""
    if fake_ai.enabled():
        t0 = time.time()
        data = fake_ai.answer(prompt_text)
        if usage is not None:
            usage.add_call(len(prompt_text) // 2, 200, time.time() - t0)
        return data

    tokens = max_tokens
    bad_text = ""
    grown = False
    tries = 0
    while tries < 2:
        text, stop = _call_with_retry(prompt_text, tokens, thinking, usage)
        try:
            return cut_json(text)
        except (ValueError, json.JSONDecodeError):
            bad_text = text
            if stop == "max_tokens" and not grown and tokens < MAX_TOKENS_CEILING:
                # 상한에 걸려 잘렸다: 상한을 두 배로 늘려 한 번 더 (이 시도는 재요청 횟수에 넣지 않음)
                tokens = min(tokens * 2, MAX_TOKENS_CEILING)
                grown = True
                continue
            tries += 1
    raise BadJSONError("JSON을 읽지 못함: " + (bad_text[:300] if bad_text else "(빈 답)"))
