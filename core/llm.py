"""모든 언어 모델 호출이 거치는 곳. ask_json() 하나로 통일한다(규칙 4).

- anthropic 공식 SDK, 스트리밍으로 받아 최종 메시지를 합친다.
- 네트워크·429·5xx는 2초→4초 기다린 뒤 최대 2회 더.
- JSON을 읽지 못하면 같은 요청을 1회 더(잘렸으면 상한을 두 배로), 그래도 안 되면 E-08.
- 키는 환경변수 ANTHROPIC_API_KEY에서 읽는다(app.py가 st.secrets 값을 먼저 넣어 준다).
"""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import config

# 모든 호출에 붙는 시스템 지시 한 줄 (BR-10 예외 1)
SYSTEM = "당신은 JSON 객체 하나만 출력합니다. 설명 문장이나 코드 블록 표시(```)를 붙이지 않습니다."


class LLMError(Exception):
    """AI 호출 오류. code와 화면 문구를 함께 들고 다닌다."""
    code = "E-07"
    user_message = "AI 서버와 연결이 어려워요. 잠시 후 다시 시도 버튼을 눌러 주세요"


class KeyMissingError(LLMError):
    code = "E-06"
    user_message = "AI 키가 설정되지 않았어요. README의 설정 방법을 보세요"


class APICallError(LLMError):
    code = "E-07"
    user_message = "AI 서버와 연결이 어려워요. 잠시 후 다시 시도 버튼을 눌러 주세요"


class JSONParseError(LLMError):
    code = "E-08"
    user_message = "AI 답을 읽지 못했어요. 다시 시도해 주세요"


@dataclass
class Usage:
    """AI 호출 수와 토큰, 걸린 시간."""
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    seconds: float = 0.0

    def add(self, input_tokens: int, output_tokens: int, seconds: float = 0.0) -> None:
        """호출 1번을 더한다."""
        self.calls += 1
        self.input_tokens += int(input_tokens or 0)
        self.output_tokens += int(output_tokens or 0)
        self.seconds += float(seconds or 0.0)

    def merge(self, other: "Usage") -> None:
        """다른 묶음을 더한다. 호출 수도 묶음 안의 호출 수만큼 는다(v1.5)."""
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.seconds += other.seconds


def fake_mode() -> bool:
    return os.environ.get("BINTM_FAKE_AI") == "1"


def has_key() -> bool:
    return fake_mode() or bool(os.environ.get("ANTHROPIC_API_KEY"))


def extract_json(text: str):
    """첫 `{`부터 마지막 `}`까지만 잘라 파싱한다."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("JSON이 없음")
    return json.loads(text[start:end + 1])


def _call_model(prompt_text: str, max_tokens: int, thinking: bool):
    """실제 호출 1회. (글, stop_reason, 입력 토큰, 출력 토큰)을 돌려준다."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=0, timeout=300.0)
    kwargs = dict(
        model=config.LLM_MODEL,
        max_tokens=max_tokens,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt_text}],
    )
    if thinking:
        kwargs["thinking"] = {"type": "adaptive"}
    with client.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()
    text = "".join(getattr(b, "text", "") for b in msg.content if b.type == "text")
    return text, msg.stop_reason, msg.usage.input_tokens, msg.usage.output_tokens


def _call_with_retry(prompt_text: str, max_tokens: int, thinking: bool):
    import anthropic

    delays = [2, 4]
    for attempt in range(3):
        try:
            return _call_model(prompt_text, max_tokens, thinking)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise KeyMissingError(f"키 오류: {type(e).__name__}") from e
        except anthropic.APIConnectionError as e:
            err = e
        except anthropic.APIStatusError as e:
            if e.status_code == 429 or e.status_code >= 500:
                err = e
            else:
                raise APICallError(f"{type(e).__name__} {e.status_code}: {e.message}") from e
        if attempt < 2:
            time.sleep(delays[attempt])
    raise APICallError(f"재시도 후 실패: {type(err).__name__}: {err}") from err


def ask_json(prompt_text: str, max_tokens: int = config.AI_MAX_TOKENS, thinking: bool = False,
             usage: Usage | None = None) -> dict:
    """프롬프트를 보내고 JSON 객체(dict)를 받는다. 호출마다 usage에 더한다."""
    if usage is None:
        usage = Usage()
    if fake_mode():
        from core import fake_ai
        t0 = time.time()
        data = fake_ai.answer(prompt_text)
        usage.add(len(prompt_text) // 2, 300, time.time() - t0)
        return data
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise KeyMissingError("ANTHROPIC_API_KEY 없음")

    tokens = max_tokens
    last_text = ""
    for _ in range(2):
        t0 = time.time()
        text, stop, in_tok, out_tok = _call_with_retry(prompt_text, tokens, thinking)
        usage.add(in_tok, out_tok, time.time() - t0)
        try:
            data = extract_json(text)
            if isinstance(data, dict):
                return data
        except (ValueError, json.JSONDecodeError):
            pass
        last_text = text
        if stop == "max_tokens":
            tokens = min(tokens * 2, config.MAX_TOKENS_CEIL)
    raise JSONParseError(f"JSON 파싱 실패. 응답 앞부분: {last_text[:300]}")


def run_parallel(tasks: dict, workers: int = 6):
    """{키: fn(usage) -> 결과}를 동시에 부른다. 스레드 안에서 화면 상태를 건드리지 않는다.

    반환: (결과 dict, 오류 dict, 합친 Usage)
    """
    total = Usage()
    results, errors = {}, {}
    if not tasks:
        return results, errors, total

    def runner(fn):
        u = Usage()
        try:
            return fn(u), None, u
        except Exception as e:  # 한 개념이 실패해도 나머지는 살린다
            return None, e, u

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(runner, fn): key for key, fn in tasks.items()}
        for fut in as_completed(futures):
            key = futures[fut]
            result, err, u = fut.result()
            total.merge(u)
            if err is None:
                results[key] = result
            else:
                errors[key] = err
    return results, errors, total


def error_code(err: Exception) -> str:
    return getattr(err, "code", "E-07") if isinstance(err, LLMError) else "E-08"


def error_message(err: Exception) -> str:
    if isinstance(err, LLMError):
        return err.user_message
    return JSONParseError.user_message
