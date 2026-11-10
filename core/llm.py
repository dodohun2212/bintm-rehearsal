# 모든 언어 모델 호출은 ask_json() 하나를 거친다 (7.3).
import json
import os
import time
from dataclasses import dataclass

import config

# BR-10 예외 1: 모든 호출에 붙는 시스템 지시 한 줄
SYSTEM_JSON = "JSON 객체 하나만 출력한다. 설명 문장이나 코드 블록 표시(```)를 붙이지 않는다."

MAX_TOKENS_CAP = 16000
RETRY_WAITS = (2, 4)


class LLMError(Exception):
    code = "E-07"


class NoKeyError(LLMError):
    code = "E-06"


class APICallError(LLMError):
    code = "E-07"


class BadJSONError(LLMError):
    code = "E-08"


@dataclass
class Usage:
    """AI 호출 수와 토큰, 걸린 시간."""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    def add(self, input_tokens: int, output_tokens: int, seconds: float = 0.0) -> None:
        self.calls += 1
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        self.seconds += float(seconds or 0.0)

    def merge(self, other: "Usage") -> None:
        # 묶음 안의 호출 수만큼 더한다 (묶음을 1번으로 세지 않는다)
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.seconds += other.seconds


def is_fake() -> bool:
    return os.environ.get("BINTM_FAKE_AI") == "1"


def has_key() -> bool:
    return is_fake() or bool(os.environ.get("ANTHROPIC_API_KEY"))


def extract_json(text: str) -> dict:
    """첫 { 부터 마지막 } 까지만 잘라 파싱한다."""
    if not text:
        raise BadJSONError("빈 응답")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise BadJSONError("JSON을 찾지 못함")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise BadJSONError(f"JSON 파싱 실패: {e}") from e
    if not isinstance(data, dict):
        raise BadJSONError("JSON 객체가 아님")
    return data


_client = None


def _get_client():
    global _client
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise NoKeyError("AI 키 없음")
    import anthropic
    if _client is None or getattr(_client, "_bintm_key", None) != key:
        _client = anthropic.Anthropic(api_key=key, max_retries=0, timeout=300.0)
        _client._bintm_key = key
    return _client


def _call(prompt_text: str, max_tokens: int, thinking: bool):
    """한 번 호출. (글, stop_reason, 입력 토큰, 출력 토큰)을 돌려준다. 테스트에서 바꿔 끼운다."""
    client = _get_client()
    kwargs = dict(
        model=config.LLM_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_JSON,
        messages=[{"role": "user", "content": prompt_text}],
    )
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    with client.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return text, msg.stop_reason, msg.usage.input_tokens, msg.usage.output_tokens


def _call_with_retry(prompt_text: str, max_tokens: int, thinking: bool):
    import anthropic
    last = None
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            return _call(prompt_text, max_tokens, thinking)
        except NoKeyError:
            raise
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise NoKeyError(f"AI 키 오류: {type(e).__name__}") from e
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as e:
            last = e
        except anthropic.APIStatusError as e:
            if e.status_code >= 500 or e.status_code == 429:
                last = e
            else:
                raise APICallError(f"AI 요청 오류 {e.status_code}: {e.message}") from e
        if attempt < len(RETRY_WAITS):
            time.sleep(RETRY_WAITS[attempt])
    raise APICallError(f"AI 서버 연결 실패: {type(last).__name__}: {last}")


def ask_json(prompt_text: str, max_tokens: int | None = None, thinking: bool = False,
             usage: Usage | None = None) -> dict:
    """프롬프트를 보내고 JSON(dict)을 받는다. 파싱 실패는 1회 더, 잘리면 상한을 두 배로."""
    if is_fake():
        from core import fake_ai
        if usage is not None:
            usage.add(0, 0, 0.0)
        return fake_ai.answer(prompt_text)
    tokens = int(max_tokens or config.AI_MAX_TOKENS)
    last_err = None
    for _ in range(2):
        t0 = time.time()
        text, stop_reason, tin, tout = _call_with_retry(prompt_text, tokens, thinking)
        if usage is not None:
            usage.add(tin, tout, time.time() - t0)
        if stop_reason == "refusal":
            raise APICallError("AI가 답하지 않음(refusal)")
        try:
            return extract_json(text)
        except BadJSONError as e:
            last_err = e
            if stop_reason == "max_tokens":
                tokens = min(tokens * 2, MAX_TOKENS_CAP)
    raise BadJSONError(f"AI 답을 JSON으로 읽지 못함: {last_err}")
