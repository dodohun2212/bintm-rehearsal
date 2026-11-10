"""화면 공용: 세션 초기화, 키 읽기, 비용 보호 연결, 에러 문구, 배지·카드 HTML, 진행 막대와 동시 호출."""
from __future__ import annotations

import copy
import html
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st

import config
from core import guard, llm
from core.export import rich
from core.llm import Usage

DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다"
SEND_NOTICE = "올린 자료와 녹음은 분석을 위해 AI 제공사(Anthropic, OpenAI) 서버로 전송됩니다."
STORE_NOTICE = ("올린 파일과 결과는 서버 디스크에 저장하지 않아요. 결과는 이 브라우저 화면(세션)에만 있고, "
                "같은 파일을 다시 분석할 때를 위해 개념·강조 분석 결과와 쪽 그림만 서버 메모리에 잠시 둬요(서버가 다시 켜지면 사라져요).")
STEP_NAMES = {1: "① 자료 올리기", 2: "② 출제 포인트", 3: "③ 취약점 진단", 4: "④ 공부 순서", 5: "⑤ 안내·설정"}

ERRORS = {
    "E-01": "PDF나 PPTX만 올릴 수 있어요. 한글(hwp)은 파일 → PDF로 저장해 주세요",
    "E-02": "파일이 너무 커요(최대 30MB). 한 장만 따로 저장해 올려 주세요",
    "E-03": "이 PDF는 글자가 그림으로 들어 있어 읽을 수 없어요. 글자가 선택되는 PDF를 올려 주세요",
    "E-04": "녹음은 m4a/mp3/wav 25MB까지예요. 길면 앞부분만 잘라 올리거나 대본 붙여넣기를 써 주세요",
    "E-05": "녹음을 글자로 바꾸지 못해 녹음 없이 계산했어요. 대본 붙여넣기로 다시 분석할 수 있어요",
    "E-06": "AI 키가 설정되지 않았어요. README의 설정 방법을 보세요",
    "E-07": "AI 서버와 연결이 어려워요. 잠시 후 다시 시도 버튼을 눌러 주세요",
    "E-08": "AI 답을 읽지 못했어요. 다시 시도해 주세요",
    "E-09": "이 자료에서 개념을 찾지 못했어요. 강의 슬라이드나 교재 한 장인지 확인해 주세요",
    "E-10": "녹음에서 강조한 말을 찾지 못했어요. 자료만으로 점수를 계산했어요",
    "E-11": "아직 답하지 않았어요. 모르면 '모르겠어요'를 골라 주세요.",
    "E-13": f"앞 {config.MAX_PAGES}쪽만 분석해요. 한 장씩 올리면 더 정확해요",
    "E-14": "새로고침하면 결과가 사라져요. 결과는 ④에서 내려받기로 저장할 수 있어요",
    "E-16": f"이 화면에서는 분석을 {config.MAX_ANALYSES_PER_SESSION}번까지 할 수 있어요. 지금 결과는 ②~④에서 계속 볼 수 있어요.",
    "E-17": "오늘 이 앱에서 쓸 수 있는 분석 횟수를 다 썼어요. 내일 다시 이용해 주세요. 직접 실행하려면 README의 로컬 실행 방법을 보세요.",
    "E-99": "알 수 없는 오류가 났어요. 처음부터 다시 해 주세요",
}

# 4.3 세션 상태 키와 기본값
DEFAULTS = {
    "step": 1, "material": None, "material_bytes": None, "transcript": None, "transcript_source": None,
    "concepts": None, "meta_pages": [], "utterances": [], "scores": None, "q_mode": "섞어서", "quick_diag": False,
    "diag_ids": [], "questions": {}, "q_store": {}, "q_fail_store": {}, "answers": {}, "dont_know": {},
    "mcq_choice": {}, "show_missing": False, "missing_labels": [], "guessed": {}, "confusion": {}, "grading": {},
    "grade_failed": [], "grade_error": None, "q_failed": [], "priorities": [], "explanations": {},
    "explain_failed": [], "explain_error": None, "notes": {}, "notes_failed": [], "notes_error": None,
    "model_name": config.LLM_MODEL, "run_id": None, "from_sample": False, "analyses_used": 0, "usage": None,
    "step_times": {}, "errors": [], "notices": [], "skip_failed": False,
}


def init_state() -> None:
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = copy.deepcopy(value)
    if st.session_state["usage"] is None:
        st.session_state["usage"] = Usage()


def reset_all() -> None:
    """'다른 자료로 다시': 분석 횟수만 남기고 전부 지운다(입력칸 값 포함)."""
    used = st.session_state.get("analyses_used", 0)
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    init_state()
    st.session_state["analyses_used"] = used


def clear_after_analysis() -> None:
    """새 분석을 하면 ③④ 결과와 입력칸 값을 지운다."""
    for key in ("questions", "q_store", "q_fail_store", "answers", "dont_know", "mcq_choice", "guessed", "confusion",
                "grading", "explanations", "notes"):
        st.session_state[key] = {}
    for key in ("grade_failed", "q_failed", "priorities", "explain_failed", "notes_failed", "missing_labels", "notices"):
        st.session_state[key] = []
    st.session_state.update(show_missing=False, grade_error=None, explain_error=None, notes_error=None, skip_failed=False)
    for key in list(st.session_state.keys()):
        if isinstance(key, str) and key.startswith(("ans_", "dk_", "mcq_", "guess_", "conf_", "w_")):
            del st.session_state[key]


def load_secrets() -> None:
    """키는 st.secrets → 환경변수 순으로 찾는다. st.secrets에 있으면 환경변수로 옮겨 core가 읽게 한다."""
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        try:
            value = st.secrets.get(name)
        except Exception:  # secrets.toml이 없으면 예외
            value = None
        if value and not os.environ.get(name):
            os.environ[name] = str(value)


# ---------- 비용 보호 (F14) ----------
@st.cache_resource
def daily_analyses() -> guard.DailyCounter:
    return guard.DailyCounter(config.MAX_ANALYSES_PER_DAY)


@st.cache_resource
def daily_calls() -> guard.DailyCounter:
    return guard.DailyCounter(config.MAX_AI_CALLS_PER_DAY)


@st.cache_resource
def sample_cache() -> guard.ResultCache:
    return guard.ResultCache(max_items=200)


def take_analysis() -> str | None:
    """분석 1번을 쓴다. 쓸 수 없으면 에러 번호(E-16/E-17)."""
    if guard.session_left(st.session_state["analyses_used"], config.MAX_ANALYSES_PER_SESSION) == 0:
        return "E-16"
    if daily_calls().exhausted() or not daily_analyses().try_take():
        return "E-17"
    st.session_state["analyses_used"] += 1
    return None


def give_back_analysis() -> None:
    """AI를 부르기 전에 실패: 세션·하루 횟수를 하나씩 돌려준다."""
    st.session_state["analyses_used"] = max(0, st.session_state["analyses_used"] - 1)
    daily_analyses().give_back()


def give_back_daily_only() -> None:
    """저장된 결과만으로 끝난 분석(AI 호출 0번): 하루 횟수에서 빼지 않는다."""
    daily_analyses().give_back()


def ai_blocked() -> bool:
    """하루 AI 호출 상한에 닿았으면 새 AI 작업을 시작하지 않는다."""
    return daily_calls().exhausted()


def add_usage(usage: Usage, step: str | None = None, seconds: float | None = None) -> None:
    """사용량을 세션에 더한다(호출 수는 묶음 안의 호출 수만큼). 하루 AI 호출 수에도 더한다."""
    st.session_state["usage"].merge(usage)
    daily_calls().add(usage.calls)
    if step and seconds is not None:
        times = st.session_state["step_times"]
        times[step] = times.get(step, 0.0) + seconds  # 같은 단계를 여러 번 하면 더한다


# ---------- 에러 ----------
def error_code(exc: Exception) -> str:
    if isinstance(exc, llm.KeyMissingError):
        return "E-06"
    if isinstance(exc, llm.BadJSONError):
        return "E-08"
    if isinstance(exc, llm.LLMError):
        return "E-07"
    return "E-99"


def show_error(code: str, detail: str | None = None) -> None:
    st.error(f"{ERRORS.get(code, ERRORS['E-99'])} ({code})")
    if detail:
        with st.expander("자세한 오류"):
            st.code(detail[:2000])


# ---------- HTML ----------
def esc(text) -> str:
    return html.escape("" if text is None else str(text))


STATUS_CLASS = {"앎": "b-ok", "헷갈림": "b-mid", "모름": "b-bad", "진단 안 함": "b-none"}


def badge(text: str, cls: str = "") -> str:
    return f'<span class="bt-badge {cls}">{esc(text)}</span>'


def status_badge(status: str) -> str:
    return badge(status, STATUS_CLASS.get(status, "b-none"))


def page_badges(pages) -> str:
    return "".join(f'<span class="bt-pg">p.{int(p)}</span>' for p in pages or [])


def html_block(body: str) -> None:
    st.html(f'<div class="bt">{body}</div>')


def stats(items: list[tuple[str, object]]) -> None:
    cells = "".join(f'<div class="bt-stat"><span>{esc(k)}</span><b>{esc(v)}</b></div>' for k, v in items)
    html_block(f'<div class="bt-stats">{cells}</div>')


def step_bar(current: int) -> None:
    parts = []
    for n in (1, 2, 3, 4):
        cls = "on" if n == current else ""
        parts.append(f'<span class="{cls}">{esc(STEP_NAMES[n])}</span>')
    html_block('<div class="bt-steps">' + ' <i>›</i> '.join(parts) + "</div>")


def header(step: int, title: str, sub: str) -> None:
    step_bar(step)
    st.markdown(f"## {title}")
    st.caption(sub)


def paragraphs(text: str | None) -> str:
    import re

    parts = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    return "".join(f"<p>{rich(p)}</p>" for p in parts)


# ---------- 동시 호출과 진행 막대 ----------
def run_parallel(fn, items: dict, label: str, workers: int = 6):
    """items {key: 인자}를 스레드로 동시에 부른다. fn(인자, usage)는 세션을 읽지 않는다.

    메인 스레드에서 as_completed로 하나씩 받으며 진행 막대 "label k / n"을 늘린다.
    돌려주는 것: (결과 dict, 실패 dict {key: 예외}, 합친 Usage, 걸린 초)
    """
    results, errors, total = {}, {}, Usage()
    if not items:
        return results, errors, total, 0.0
    started = time.perf_counter()

    def task(arg):
        usage = Usage()
        try:
            return fn(arg, usage), usage, None
        except Exception as exc:  # 한 개념이 실패해도 나머지는 살린다
            return None, usage, exc

    n = len(items)
    bar = st.progress(0.0, text=f"{label} 0 / {n}")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(task, arg): key for key, arg in items.items()}
        for k, fut in enumerate(as_completed(futures), start=1):
            key = futures[fut]
            result, usage, exc = fut.result()
            total.merge(usage)
            if exc is None:
                results[key] = result
            else:
                errors[key] = exc
            bar.progress(k / n, text=f"{label} {k} / {n}")
    bar.empty()
    return results, errors, total, time.perf_counter() - started


def first_error_text(errors: dict) -> str | None:
    if not errors:
        return None
    exc = next(iter(errors.values()))
    return f"{type(exc).__name__}: {exc}"


def failure_message(errors: dict) -> tuple[str, str]:
    """실패 원인에 맞는 문구와 코드(키 E-06 · 연결 E-07 · 답 형식 E-08)."""
    codes = [error_code(e) for e in errors.values()]
    for code in ("E-06", "E-07", "E-08"):
        if code in codes:
            return ERRORS[code], code
    return ERRORS["E-07"], "E-07"


CSS = """
<style>
.block-container{max-width:860px;padding-top:4.5rem;padding-bottom:6rem}
html,body,[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li{font-size:17px;line-height:1.75}
.bt{font-size:17px;line-height:1.75}
.bt p{margin:0 0 .6em 0}
.bt-steps{font-size:14px;color:#6b7280;margin-bottom:4px;overflow-wrap:anywhere}
.bt-steps span.on{color:#2563eb;font-weight:700}
.bt-steps i{font-style:normal;color:#9ca3af;margin:0 4px}
.bt-stats{display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 10px}
.bt-stat{flex:1;min-width:100px;border:1px solid rgba(128,128,128,.35);border-radius:12px;padding:8px 14px}
.bt-stat span{font-size:13px;opacity:.8;display:block}
.bt-stat b{font-size:26px}
.bt-badge{display:inline-block;border-radius:999px;padding:0 10px;font-size:13px;margin:2px 4px 2px 0;
border:1px solid rgba(128,128,128,.4)}
.b-ok{background:#dcfce7;color:#166534;border-color:#86efac}
.b-mid{background:#fef9c3;color:#854d0e;border-color:#fde047}
.b-bad{background:#fee2e2;color:#991b1b;border-color:#fca5a5}
.b-none{opacity:.75}
.b-blue{background:#dbeafe;color:#1e40af;border-color:#93c5fd}
.b-minus{text-decoration:line-through;opacity:.6}
.bt-pg{display:inline-block;background:#dbeafe;color:#1e40af;border-radius:6px;padding:0 6px;font-size:12px;margin:0 2px}
.pg{display:inline-block;background:#dbeafe;color:#1e40af;border-radius:6px;padding:0 6px;font-size:12px;margin:0 2px}
.rec{display:inline-block;background:#ede9fe;color:#5b21b6;border-radius:6px;padding:0 6px;font-size:12px;margin:0 2px}
.bt-row{display:flex;align-items:center;gap:10px;padding:7px 0;border-bottom:1px dashed rgba(128,128,128,.3);flex-wrap:wrap}
.bt-row .nm{flex:1 1 220px;font-weight:600}
.bt-row.dim{opacity:.5}
.bt-bar{height:9px;width:120px;background:rgba(128,128,128,.25);border-radius:5px;overflow:hidden;display:inline-block}
.bt-bar i{display:block;height:100%;background:#2563eb}
.bt-q{font-size:18px;font-weight:600;margin:4px 0 8px}
.bt-gap{border-left:4px solid #dc2626;padding:4px 12px;margin:8px 0}
.bt-reply{border-left:4px solid #2563eb;padding:4px 12px;margin:8px 0}
.bt-nf{background:#fffbeb;color:#78350f;border:1px solid #f59e0b;border-radius:8px;padding:6px 12px;margin:8px 0}
.bt-red{color:#dc2626;font-weight:600}
.bt-choice{padding:2px 8px;border-radius:6px;margin:2px 0}
.bt-right{background:#dcfce7;color:#166534}
.bt-wrong{background:#fee2e2;color:#991b1b}
.fig-cap{font-size:13px;opacity:.8}
/* 기다리는 안내를 화면 아래 가운데에 고정 */
[data-testid="stSpinner"]{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:1000;
background:#1e3a8a;color:#ffffff;padding:10px 18px;border-radius:999px;box-shadow:0 4px 14px rgba(0,0,0,.25)}
[data-testid="stSpinner"] *{color:#ffffff}
@media (max-width:640px){.block-container{padding-left:1rem;padding-right:1rem}.bt-bar{width:80px}}
</style>
"""
