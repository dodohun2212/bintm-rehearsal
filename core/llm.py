"""언어 모델 호출을 하나로 모은 곳. 앱의 다른 코드는 ask_json()만 부른다."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

import config

# 모든 호출에 붙는 시스템 지시 한 줄 (BR-10 예외 ①)
SYSTEM_PROMPT = "JSON만 출력하세요. 설명 문장이나 코드 블록 표시(```) 없이 JSON 객체 하나만 출력합니다."

MAX_TOKENS_CAP = 16000
RETRY_WAITS = (2, 4)  # 네트워크·429·5xx 재시도 대기(초)


class LLMError(Exception):
    """AI 호출 실패의 공통 부모. code는 화면 에러 번호."""

    code = "E-07"


class KeyMissingError(LLMError):
    code = "E-06"


class ConnectError(LLMError):
    code = "E-07"


class BadJSONError(LLMError):
    code = "E-08"


@dataclass
class Usage:
    """AI 호출 수·토큰·시간. 스레드마다 하나씩 만들고 merge로 합친다."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    def add(self, input_tokens: int, output_tokens: int, seconds: float = 0.0) -> None:
        self.calls += 1
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        self.seconds += float(seconds or 0.0)

    def merge(self, other: "Usage | None") -> None:
        # 묶음을 1번으로 세지 않고, 묶음 안의 호출 수만큼 더한다
        if other is None:
            return
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.seconds += other.seconds


def fake_mode() -> bool:
    return os.environ.get("BINTM_FAKE_AI", "") == "1"


def get_key(name: str = "ANTHROPIC_API_KEY") -> str | None:
    """키는 환경변수에서 읽는다. 화면(app.py)이 st.secrets 값을 먼저 환경변수로 옮겨 둔다."""
    value = os.environ.get(name, "").strip()
    return value or None


def has_llm_key() -> bool:
    return fake_mode() or get_key("ANTHROPIC_API_KEY") is not None


def extract_json(text: str) -> dict:
    """응답에서 첫 '{'부터 마지막 '}'까지만 잘라 파싱한다."""
    if text is None:
        raise ValueError("빈 응답")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON 객체를 찾지 못함")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아님")
    return data


def call_model(prompt_text: str, max_tokens: int, thinking: bool) -> tuple[str, str, int, int]:
    """실제 API를 한 번 부른다. (글, stop_reason, 입력 토큰, 출력 토큰)을 돌려준다."""
    import anthropic

    key = get_key("ANTHROPIC_API_KEY")
    if not key:
        raise KeyMissingError("ANTHROPIC_API_KEY가 없음")
    client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=300)
    kwargs = dict(
        model=config.LLM_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_text}],
    )
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    with client.messages.stream(**kwargs) as stream:
        message = stream.get_final_message()
    text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text")
    usage = message.usage
    return text, str(message.stop_reason), int(usage.input_tokens or 0), int(usage.output_tokens or 0)


def _is_retryable(exc: Exception) -> bool:
    try:
        import anthropic
    except Exception:  # pragma: no cover
        return False
    if isinstance(exc, (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError)):
        return True
    if isinstance(exc, anthropic.APIStatusError):
        return int(getattr(exc, "status_code", 0) or 0) >= 500
    return False


def _is_auth_error(exc: Exception) -> bool:
    try:
        import anthropic
    except Exception:  # pragma: no cover
        return False
    return isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError))


def _call_with_retry(prompt_text: str, max_tokens: int, thinking: bool, usage: Usage | None):
    last: Exception | None = None
    for attempt in range(len(RETRY_WAITS) + 1):
        started = time.perf_counter()
        try:
            result = call_model(prompt_text, max_tokens, thinking)
        except KeyMissingError:
            raise
        except Exception as exc:  # 네트워크·429·5xx만 다시
            if _is_auth_error(exc):
                raise KeyMissingError(f"키 오류: {type(exc).__name__}") from exc
            last = exc
            if _is_retryable(exc) and attempt < len(RETRY_WAITS):
                time.sleep(RETRY_WAITS[attempt])
                continue
            raise ConnectError(f"{type(exc).__name__}: {exc}") from exc
        if usage is not None:
            usage.add(result[2], result[3], time.perf_counter() - started)
        return result
    raise ConnectError(str(last))  # pragma: no cover


def ask_json(
    prompt_text: str,
    max_tokens: int = config.AI_MAX_TOKENS,
    thinking: bool = False,
    usage: Usage | None = None,
) -> dict:
    """프롬프트를 보내고 JSON(dict)을 받는다.

    - 가짜 AI 모드(BINTM_FAKE_AI=1)면 core.fake_ai가 답한다.
    - JSON이 아니면 같은 요청을 1번 더. 상한에 걸려 잘렸으면 상한을 두 배로(최대 16000).
    - 그래도 실패하면 BadJSONError(E-08).
    """
    if fake_mode():
        from core import fake_ai

        if usage is not None:
            usage.add(len(prompt_text) // 4, 200, 0.0)
        return fake_ai.answer(prompt_text)

    tokens = max_tokens
    last_text = ""
    for _ in range(2):
        text, stop_reason, _, _ = _call_with_retry(prompt_text, tokens, thinking, usage)
        last_text = text
        try:
            return extract_json(text)
        except (ValueError, json.JSONDecodeError):
            if stop_reason == "max_tokens":
                tokens = min(tokens * 2, MAX_TOKENS_CAP)
    raise BadJSONError("AI 답을 JSON으로 읽지 못함: " + (last_text or "")[:300])
