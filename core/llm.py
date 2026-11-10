"""모든 언어 모델 호출은 ask_json() 하나를 거친다 (BR-02, 7.3)."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass

import config

# 모든 호출에 붙는 시스템 지시 한 줄 (BR-10 예외 1)
SYSTEM_PROMPT = "JSON만 출력합니다. 설명 문장이나 코드 블록 표시 없이 JSON 객체 하나만 답합니다."

RETRY_WAITS = (2, 4)  # 네트워크·429·5xx 재시도 대기(초)

ERROR_TEXT = {
    "E-06": "AI 키가 설정되지 않았어요. README의 설정 방법을 보세요",
    "E-07": "AI 서버와 연결이 어려워요. 잠시 후 다시 시도 버튼을 눌러 주세요",
    "E-08": "AI 답을 읽지 못했어요. 다시 시도해 주세요",
}

_keys: dict[str, str] = {}


class LLMError(Exception):
    """AI 호출 실패. code는 9장 에러 번호."""
    code = "E-07"


class KeyMissingError(LLMError):
    code = "E-06"


class ConnectError(LLMError):
    code = "E-07"


class BadJsonError(LLMError):
    code = "E-08"


def error_info(exc: Exception) -> tuple[str, str]:
    """예외 → (에러 번호, 화면 문구). 문구에 키·경로를 넣지 않는다."""
    code = getattr(exc, "code", "E-07") if isinstance(exc, LLMError) else "E-07"
    return code, ERROR_TEXT.get(code, ERROR_TEXT["E-07"])


def set_keys(values: dict) -> None:
    """화면(app.py)이 st.secrets에서 읽은 키를 넘긴다. 없으면 환경변수를 쓴다."""
    for name, value in values.items():
        if value:
            _keys[name] = str(value)


def get_key(name: str) -> str | None:
    return _keys.get(name) or os.environ.get(name) or None


def fake_mode() -> bool:
    return os.environ.get("BINTM_FAKE_AI") == "1"


def has_llm_key() -> bool:
    return fake_mode() or bool(get_key("ANTHROPIC_API_KEY"))


@dataclass
class Usage:
    """AI 사용량. 호출마다 calls를 1 늘린다. 저장된 결과를 다시 쓰면 더하지 않는다."""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    def add(self, input_tokens: int, output_tokens: int, seconds: float) -> None:
        self.calls += 1
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        self.seconds += float(seconds or 0)

    def merge(self, other: "Usage | None") -> None:
        """다른 묶음(스레드에서 쓴 사용량)을 더한다. 호출 수도 묶음 안의 호출 수만큼 는다."""
        if other is None:
            return
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.seconds += other.seconds


def parse_json(text: str) -> dict:
    """첫 `{`부터 마지막 `}`까지만 잘라 파싱한다."""
    if not text:
        raise ValueError("빈 답")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON 없음")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("JSON 객체가 아님")
    return data


_client_lock = threading.Lock()
_client_cache: dict[str, object] = {}


def _client():
    key = get_key("ANTHROPIC_API_KEY")
    if not key:
        raise KeyMissingError("ANTHROPIC_API_KEY 없음")
    import anthropic
    with _client_lock:
        if key not in _client_cache:
            _client_cache.clear()
            _client_cache[key] = anthropic.Anthropic(api_key=key, max_retries=0, timeout=300.0)
        return _client_cache[key]


def _send_real(prompt_text: str, max_tokens: int, thinking: bool):
    """실제 호출 1번. (글, stop_reason, 입력 토큰, 출력 토큰)을 돌려준다."""
    client = _client()
    kwargs = dict(
        model=config.LLM_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt_text}],
    )
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    with client.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()
    text = "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text")
    usage = getattr(msg, "usage", None)
    return (text, msg.stop_reason,
            getattr(usage, "input_tokens", 0) or 0, getattr(usage, "output_tokens", 0) or 0)


def _send_with_retry(send, prompt_text: str, max_tokens: int, thinking: bool):
    """네트워크·429·5xx는 2초→4초 기다리고 최대 2번 더."""
    import anthropic
    last = None
    for attempt in range(len(RETRY_WAITS) + 1):
        try:
            return send(prompt_text, max_tokens, thinking)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as exc:
            raise KeyMissingError(f"키 오류: {type(exc).__name__}") from exc
        except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError) as exc:
            last = exc
        except anthropic.APIStatusError as exc:
            if getattr(exc, "status_code", 0) >= 500:
                last = exc
            else:
                raise ConnectError(f"요청 오류 {getattr(exc, 'status_code', '')}: {exc}") from exc
        if attempt < len(RETRY_WAITS):
            time.sleep(RETRY_WAITS[attempt])
    raise ConnectError(f"연결 실패: {type(last).__name__}: {last}")


def ask_json(prompt_text: str, max_tokens: int | None = None, thinking: bool = False,
             usage: Usage | None = None, _send=None) -> dict:
    """프롬프트를 보내 JSON(dict)을 받는다.

    - 답이 상한에 걸려 JSON이 잘리면 상한을 두 배(최대 16000)로 늘려 한 번 더.
    - 그 밖의 파싱 실패는 같은 요청을 1번 더, 또 실패하면 BadJsonError(E-08).
    """
    if _send is None and fake_mode():
        from core import fake_ai
        t0 = time.time()
        data = fake_ai.answer(prompt_text)
        if usage is not None:
            usage.add(len(prompt_text) // 3, len(json.dumps(data, ensure_ascii=False)) // 3, time.time() - t0)
        return data
    send = _send or _send_real
    tokens = max_tokens or config.AI_MAX_TOKENS
    grown = False
    parse_retry = 0
    last_err = ""
    while True:
        t0 = time.time()
        text, stop, in_tok, out_tok = _send_with_retry(send, prompt_text, tokens, thinking)
        if usage is not None:
            usage.add(in_tok, out_tok, time.time() - t0)
        if stop == "refusal":
            raise BadJsonError("AI가 답을 거절했어요(refusal)")
        try:
            return parse_json(text)
        except (ValueError, json.JSONDecodeError) as exc:
            last_err = f"{exc} / 답 앞부분: {(text or '')[:300]}"
            if stop == "max_tokens" and not grown and tokens < config.RETRY_MAX_TOKENS:
                tokens = min(tokens * 2, config.RETRY_MAX_TOKENS)
                grown = True
                continue
            if parse_retry < 1:
                parse_retry += 1
                continue
            raise BadJsonError(f"JSON 파싱 실패: {last_err}") from exc
