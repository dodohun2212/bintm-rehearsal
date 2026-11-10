"""화면 공용: 세션 키(한 곳), 초기화, 배지·카드 HTML, 진행 막대, 동시 호출, 사용량."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import streamlit as st

import config
from core import llm
from core.diagnose import evidence_pages
from core.extract import pages_text
from core.guard import DailyCounter, ResultCache
from core.html import CSS, esc

S = st.session_state

# 세션 키는 모두 여기 한 곳에 기본값과 함께 둔다 (4.3)
DEFAULTS = {
    "step": 1,
    "material": None, "material_bytes": None, "transcript": None, "transcript_source": None,
    "concepts": None, "meta_pages": [], "utterances": [], "scores": None,
    "q_mode": "섞어서", "quick_diag": False, "diag_ids": [],
    "q_store": {}, "q_failed": [], "q_error": None, "questions": {},
    "answers": {}, "dont_know": {}, "mcq_choice": {}, "guessed": {}, "confusion": {}, "show_missing": False,
    "grading": {}, "grade_failed": [], "grade_error": None,
    "priorities": None, "explanations": {}, "explain_failed": [], "explain_error": None,
    "notes": {}, "notes_failed": [], "notes_error": None, "notes_started": False,
    "view": "🎯 공부 순서와 오답노트",
    "run_id": None, "from_sample": False, "loaded_from_json": False,
    "analyses_used": 0, "usage": None, "errors": [], "notices": [], "model_name": config.LLM_MODEL,
}
KEEP_ON_RESET = ("analyses_used",)  # "다른 자료로 다시"로도 지우지 않는 키
WIDGET_PREFIXES = ("ans_", "dk_", "mcq_", "guess_", "conf_")

ERR = {
    "E-01": "PDF나 PPTX만 올릴 수 있어요. 한글(hwp)은 파일 → PDF로 저장해 주세요",
    "E-02": f"파일이 너무 커요(최대 {config.MAX_MATERIAL_MB}MB). 한 장만 따로 저장해 올려 주세요",
    "E-03": "이 PDF는 글자가 그림으로 들어 있어 읽을 수 없어요. 글자가 선택되는 PDF를 올려 주세요",
    "E-04": f"녹음은 m4a/mp3/wav {config.MAX_AUDIO_MB}MB까지예요. 길면 앞부분만 잘라 올리거나 대본 붙여넣기를 써 주세요",
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
    "UNKNOWN": "알 수 없는 오류가 났어요. 처음부터 다시 해 주세요",
}
STEP_NAMES = ["① 자료 올리기", "② 출제 포인트", "③ 취약점 진단", "④ 공부 순서", "⑤ 안내·설정"]

PAGE_CSS = """
<style>
.block-container{max-width:860px;padding-top:4.5rem;padding-bottom:5rem}
html,body,[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li{font-size:17px;line-height:1.75}
[data-testid="stSpinner"]{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);z-index:1000;
  background:#1e3a8a;color:#fff;padding:8px 18px;border-radius:999px;box-shadow:0 4px 14px rgba(0,0,0,.25)}
[data-testid="stSpinner"] *{color:#fff !important}
.bt-steps{font-size:.92em;color:#64748b;margin-bottom:4px}
.bt-steps b{color:#2563eb}
.bt-stat{border:1px solid #d0d7e2;border-radius:10px;padding:8px 12px;text-align:center}
.bt-stat b{display:block;font-size:1.6em}
@media (max-width:640px){.block-container{padding-left:1rem;padding-right:1rem}}
""" + CSS + "</style>"


def init_state() -> None:
    for k, v in DEFAULTS.items():
        if k not in S:
            S[k] = _fresh(v)
    if S["usage"] is None:
        S["usage"] = llm.Usage().to_dict()


def _fresh(v):
    if isinstance(v, dict):
        return dict(v)
    if isinstance(v, list):
        return list(v)
    return v


def reset_state(keep_step: bool = False) -> None:
    """'다른 자료로 다시': 세션 키를 전부 지우고 분석 횟수만 남긴다."""
    for k in list(S.keys()):
        if k in KEEP_ON_RESET:
            continue
        if k in DEFAULTS or k.startswith(WIDGET_PREFIXES) or k.startswith("bt_"):
            del S[k]
    init_state()


def clear_results_for_new_analysis() -> None:
    """새 분석을 시작하기 전에 지난 결과를 지운다(사용량·분석 횟수는 남김)."""
    keep_usage = S.get("usage")
    used = S.get("analyses_used", 0)
    reset_state()
    S["usage"] = keep_usage or llm.Usage().to_dict()
    S["analyses_used"] = used


@st.cache_resource
def counters() -> dict:
    """서버에 하나: 하루 분석 횟수, 하루 AI 호출 수."""
    return {"analyses": DailyCounter(config.MAX_ANALYSES_PER_DAY),
            "ai_calls": DailyCounter(config.MAX_AI_CALLS_PER_DAY)}


@st.cache_resource
def sample_cache() -> ResultCache:
    """서버에 하나: 샘플 자료의 문제·설명·노트 재사용."""
    return ResultCache(max_items=200)


def usage() -> llm.Usage:
    return llm.Usage.from_dict(S["usage"])


def add_usage(u: llm.Usage) -> None:
    """세션 사용량에 더하고, 서버 하루 AI 호출 수에도 더한다(저장된 결과는 여기 오지 않는다)."""
    total = usage()
    total.merge(u)
    S["usage"] = total.to_dict()
    if u.calls:
        counters()["ai_calls"].add(u.calls)


def add_stage_time(name: str, secs: float) -> None:
    total = usage()
    total.add_stage(name, secs)
    S["usage"] = total.to_dict()


def ai_budget_ok() -> bool:
    """서버 하루 AI 호출 상한을 넘었으면 새 AI 작업을 시작하지 않는다(E-17)."""
    if counters()["ai_calls"].exhausted():
        show_error("E-17")
        return False
    return True


def html(s: str) -> None:
    st.html(s)


def show_error(code: str, detail: str | None = None, message: str | None = None) -> None:
    st.error(f"{message or ERR.get(code, ERR['UNKNOWN'])} ({code})" if code != "UNKNOWN" else ERR["UNKNOWN"])
    if detail:
        with st.expander("자세한 오류"):
            st.code(str(detail)[:2000])


def error_of(e: Exception) -> tuple[str, str]:
    """예외 → (에러 번호, 화면 문구)."""
    if isinstance(e, llm.AIError):
        return e.code, ERR.get(e.code, e.message)
    return "UNKNOWN", ERR["UNKNOWN"]


def step_bar(current: int) -> None:
    parts = []
    for i, name in enumerate(STEP_NAMES[:4], 1):
        parts.append(f"<b>{esc(name)}</b>" if i == current else esc(name))
    html(f'<div class="bt-steps">{" › ".join(parts)}</div>')


def stat_row(pairs) -> None:
    cols = st.columns(len(pairs))
    for col, (label, n) in zip(cols, pairs):
        col.html(f'<div class="bt-stat"><b>{esc(n)}</b>{esc(label)}</div>')


def concept_map() -> dict:
    return {c["id"]: c for c in S["concepts"] or []}


def score_rows() -> list[dict]:
    return (S["scores"] or {}).get("scores", [])


def score_map() -> dict:
    return {r["concept_id"]: r for r in score_rows()}


def evidence(cid: str) -> tuple[list[int], str]:
    """그 개념의 근거 쪽(최대 8)과 쪽 텍스트. 스레드를 만들기 전에 메인 스레드에서 꺼낸다."""
    c = concept_map()[cid]
    pages = evidence_pages(c, S["meta_pages"])
    if not pages:
        pages = [1]
    return pages, pages_text(S["material"], pages)


def answer_info(cid: str) -> dict:
    """입력칸의 지금 값(그려진 위젯 값, 없으면 세션 딕셔너리)."""
    def cur(prefix, store, default):
        k = prefix + cid
        return S[k] if k in S else S[store].get(cid, default)

    mcq = cur("mcq_", "mcq_choice", None)
    guessed = bool(cur("guess_", "guessed", False))
    conf = cur("conf_", "confusion", "") if guessed else ""
    return {"answer": cur("ans_", "answers", ""), "dont_know": bool(cur("dk_", "dont_know", False)),
            "mcq_choice": mcq, "guessed": guessed and mcq is not None and mcq >= 0, "confusion": conf or ""}


def run_parallel(tasks: list[tuple[str, callable]], label: str, workers: int, eta: str = "") -> tuple[dict, dict]:
    """tasks: [(키, 인자 없는 함수)] → (성공 {키: 값}, 실패 {키: 예외}).
    스레드 안에서는 st를 부르지 않는다. 메인 스레드에서 as_completed로 받으며 진행 막대를 늘린다."""
    ok, fail = {}, {}
    n = len(tasks)
    if n == 0:
        return ok, fail
    bar = st.progress(0.0, text=f"{label} 0 / {n}" + (f" · {eta}" if eta else ""))
    with st.spinner(f"{label}… {eta}".strip()):
        with ThreadPoolExecutor(max_workers=min(workers, n)) as pool:
            futs = {pool.submit(fn): key for key, fn in tasks}
            done = 0
            for fut in as_completed(futs):
                key = futs[fut]
                try:
                    ok[key] = fut.result()
                except Exception as e:  # noqa: BLE001
                    fail[key] = e
                done += 1
                bar.progress(done / n, text=f"{label} {done} / {n}" + (f" · {eta}" if eta else ""))
    bar.empty()
    return ok, fail


def export_state() -> dict:
    """내려받기 파일에 넘길 세션 값(복사)."""
    keys = ("material", "transcript", "transcript_source", "concepts", "utterances", "scores", "priorities",
            "questions", "answers", "dont_know", "mcq_choice", "guessed", "confusion", "grading",
            "explanations", "notes", "meta_pages")
    return {k: S.get(k) for k in keys}


def timed(name: str):
    """with timed('단계'): … 단계별 걸린 시간을 사용량에 더한다."""
    class _T:
        def __enter__(self):
            self.t0 = time.time()
            return self

        def __exit__(self, *a):
            add_stage_time(name, time.time() - self.t0)
            return False

    return _T()
