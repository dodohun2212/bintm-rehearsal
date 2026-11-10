"""빈틈노트 화면 S01~S05와 사이드바. 계산은 core/에 있고 이 파일은 화면만 다룬다."""
from __future__ import annotations

import datetime as _dt
import hashlib
import html as _html
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent


# ---------- 재배포 뒤 예전 모듈 버리기 (v1.6, v1.9) ----------

def _changed(old: dict | None, new: dict, prompt_keys) -> bool:
    """지난 기록과 지금 파일 시각을 비교한다. 프롬프트는 기록에 없어도 바뀐 것으로 본다."""
    old = old or {}
    for k, v in new.items():
        if k not in old:
            if k in prompt_keys:
                return True
            continue
        if old[k] != v:
            return True
    return False


def _drop_stale_modules() -> None:
    files = [ROOT / "config.py"] + sorted((ROOT / "core").glob("*.py"))
    prompt_files = sorted((ROOT / "prompts").glob("*.md"))
    stamps = {str(p): p.stat().st_mtime for p in files + prompt_files if p.exists()}
    old = getattr(sys, "_bintm_stamps", None)
    if old is not None and _changed(old, stamps, {str(p) for p in prompt_files}) or (
            old is None and any(n == "config" or n.startswith("core") for n in sys.modules)):
        for name in list(sys.modules):
            if name == "config" or name == "core" or name.startswith("core."):
                del sys.modules[name]
        st.cache_resource.clear()
    sys._bintm_stamps = stamps


_drop_stale_modules()

import config  # noqa: E402
from core import prompts  # noqa: E402
from core.concepts import NoConceptsError, extract_concepts, meta_pages  # noqa: E402
from core.diagnose import (DONT_KNOW, ESSAY, EXAMPLE_CONFUSION, MCQ, MODES, choose_kind,  # noqa: E402
                           clean_confusion, diag_targets, evidence_pages, example_answers, grade_essay,
                           is_answered, local_grading, make_question)
from core.explain import make_explanation  # noqa: E402
from core.export import ACTION_DESC, notes_html, pages_badges, rich, study_html  # noqa: E402
from core.extract import ExtractError, check_audio, extract, file_hash, mask  # noqa: E402
from core.figure import figure_html  # noqa: E402
from core.guard import DailyCounter, ResultCache, session_left  # noqa: E402
from core.llm import KeyMissingError, LLMError, Usage, error_code, error_message, fake_mode, has_key, run_parallel  # noqa: E402
from core.note import detail_level, lecture_order, make_note, professor_quotes, short_note  # noqa: E402
from core.pageimg import page_jpeg  # noqa: E402
from core.priority import ACTIONS, compute_priorities, split_review  # noqa: E402
from core.score import badges, compute_scores  # noqa: E402
from core import stt  # noqa: E402
from core.utterances import TYPE_LABEL, find_utterances  # noqa: E402

st.set_page_config(page_title="빈틈노트", page_icon="📝", layout="centered")

DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다."
SCORE_NOTE = ("출제 가능성 점수는 자료와 녹음의 신호를 정해진 규칙(가중치 v0)으로 더해, 가장 높은 개념을 100점으로 맞춘 "
              "비교용 점수예요. 확률이 아니며 실제 출제를 보장하지 않습니다.")
DATA_NOTE = ("올린 자료와 녹음은 분석을 위해 AI 제공사(Anthropic, OpenAI) 서버로 전송됩니다. 올린 파일은 서버 디스크에 "
             "저장하지 않아요. 결과는 이 브라우저 탭의 세션에 두고, 같은 파일을 다시 분석할 때를 위해 개념·강조 분석 결과와 "
             "쪽 그림만 서버 메모리 캐시에 잠시 둬요(서버가 다시 켜지면 사라져요).")
SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TXT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
CHOICE_MARKS = "①②③④"
STATUS_CLASS = {"앎": "ok", "헷갈림": "mid", "모름": "bad", "진단 안 함": "none"}

CSS = """
<style>
.block-container{max-width:860px;padding-top:4.5rem}
.stMarkdown p, .stMarkdown li {font-size:17px;line-height:1.75}
[data-testid="stSpinner"]{position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%); z-index: 9999;
 background:#ffffff; border:1px solid #cbd5e1; border-radius:999px; padding:8px 20px; box-shadow:0 4px 16px rgba(0,0,0,.15)}
.bt-steps{font-size:.9em;color:#64748b;margin-bottom:.4rem}.bt-steps b{color:#2563eb}
.bt-row{border:1px solid #e2e8f0;border-radius:10px;padding:8px 12px;margin:6px 0;background:#f8fafc;color:#1f2937;line-height:1.7}
.bt-row.faded{opacity:.55}
.bt-bar{display:inline-block;height:8px;background:#e2e8f0;border-radius:4px;width:110px;vertical-align:middle}
.bt-bar i{display:block;height:8px;background:#2563eb;border-radius:4px}
.b{display:inline-block;font-size:.8em;padding:1px 8px;border-radius:10px;margin:2px 4px 2px 0;background:#e2e8f0;color:#334155}
.b.ok{background:#dcfce7;color:#15803d}.b.mid{background:#fef9c3;color:#a16207}.b.bad{background:#fee2e2;color:#b91c1c}
.b.minus{text-decoration:line-through;color:#94a3b8}
.pg{display:inline-block;font-size:.78em;padding:0 6px;border-radius:8px;background:#dbeafe;color:#1e40af}
.gap{border-left:4px solid #dc2626;padding:4px 10px;margin:8px 0}.conf{border-left:4px solid #2563eb;padding:4px 10px;margin:8px 0}
.nf{border:1px solid #eab308;background:#fef9c3;color:#713f12;padding:6px 10px;border-radius:6px;margin:8px 0}
.choice{margin:2px 0}.choice.right{color:#15803d;font-weight:600}.choice.mine{color:#b91c1c}
.info{color:#64748b;font-size:.9em}.q-text{font-size:1.08em;font-weight:600;margin:4px 0 8px}
.missing{color:#dc2626;font-weight:600}
@media (max-width: 640px){.bt-bar{width:70px}}
</style>
"""

DEFAULTS = {
    "step": 1, "material": None, "transcript": None, "transcript_source": None, "concepts": None,
    "concept_result": None, "meta": [], "utterances": [], "scores": None, "q_mode": "섞어서", "quick_diag": False,
    "diag_ids": [], "questions": {}, "qbank": {}, "q_failed": [], "q_failed_keys": {}, "answers": {},
    "dont_know": {}, "mcq_choice": {}, "show_missing": False, "guessed": {}, "confusion": {}, "grading": {},
    "grade_failed": [], "grade_error": None, "grade_error_code": None, "priorities": None, "explanations": {},
    "explain_failed": [], "explain_errors": {}, "notes": {}, "notes_failed": [], "material_bytes": None,
    "model_name": config.LLM_MODEL, "run_id": None, "from_sample": False, "usage": None, "errors": [],
    "notices": [], "auto_done": False,
}


def init_state() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v.copy() if isinstance(v, (dict, list)) else v
    if st.session_state.get("usage") is None:
        st.session_state["usage"] = Usage()
    st.session_state.setdefault("analyses_used", 0)


def reset_all() -> None:
    """'다른 자료로 다시': 세션 키를 전부 지운다. 분석 횟수만 남긴다."""
    used = st.session_state.get("analyses_used", 0)
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    init_state()
    st.session_state["analyses_used"] = used


def load_keys() -> None:
    """키는 st.secrets → 환경변수 순으로 찾는다. 코드에 키를 적지 않는다."""
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        try:
            v = st.secrets.get(k)
        except Exception:
            v = None
        if v:
            os.environ[k] = str(v)


def H(s: str) -> None:
    st.html(s)


def esc(s) -> str:
    return _html.escape("" if s is None else str(s))


def bar(v: int) -> str:
    v = max(0, min(int(v), 100))
    return f'<span class="bt-bar"><i style="width:{v}%"></i></span>'


def status_badge(status: str) -> str:
    return f'<span class="b {STATUS_CLASS.get(status, "none")}">{esc(status)}</span>'


def show_error(err: Exception, prefix: str = "") -> None:
    code = getattr(err, "code", None) or error_code(err)
    msg = getattr(err, "user_message", None) or error_message(err)
    st.error(f"{prefix}{msg} ({code})")
    with st.expander("자세한 오류"):
        st.code(f"{type(err).__name__}: {err}"[:1500])


# ---------- 서버 공용 자원 ----------

@st.cache_resource
def daily_counter() -> DailyCounter:
    return DailyCounter(config.MAX_ANALYSES_PER_DAY)


@st.cache_resource
def sample_cache() -> ResultCache:
    return ResultCache(200)


def _ver(name: str) -> str:
    return hashlib.sha1(prompts.load(name).encode("utf-8")).hexdigest()[:8]


@st.cache_data(show_spinner=False, max_entries=30)
def cached_concepts(run_id: str, prompt_ver: str, _material: dict, _sink: list) -> dict:
    u = Usage()
    res = extract_concepts(_material, u)
    _sink.append(u)  # 실제로 불렀을 때만 사용량을 더한다
    return res


@st.cache_data(show_spinner=False, max_entries=30)
def cached_utterances(run_id: str, prompt_ver: str, transcript: str, concepts_json: str, _concepts: list,
                      _sink: list) -> list:
    u = Usage()
    res = find_utterances(transcript, _concepts, u)
    _sink.append(u)
    return res


@st.cache_data(show_spinner=False, max_entries=60)
def cached_page_img(run_id: str, n: int, _data: bytes) -> bytes | None:
    return page_jpeg(_data, n)


def add_usage(u: Usage) -> None:
    st.session_state["usage"].merge(u)


# ---------- 분석 횟수 (F14) ----------

def take_analysis() -> bool:
    used = st.session_state["analyses_used"]
    if session_left(used, config.MAX_ANALYSES_PER_SESSION) == 0:
        st.session_state["errors"] = [
            f"이 화면에서는 분석을 {config.MAX_ANALYSES_PER_SESSION}번까지 할 수 있어요. 지금 결과는 ②~④에서 계속 볼 수 있어요. (E-16)"]
        return False
    if not daily_counter().try_take():
        st.session_state["errors"] = [
            "오늘 이 앱에서 쓸 수 있는 분석 횟수를 다 썼어요. 내일 다시 이용해 주세요. "
            "직접 실행하려면 README의 로컬 실행 방법을 보세요. (E-17)"]
        return False
    st.session_state["analyses_used"] = used + 1
    return True


def give_back_analysis() -> None:
    st.session_state["analyses_used"] = max(0, st.session_state["analyses_used"] - 1)
    daily_counter().give_back()


RESULT_KEYS = ["concepts", "concept_result", "meta", "utterances", "scores", "diag_ids", "questions", "qbank",
               "q_failed", "q_failed_keys", "answers", "dont_know", "mcq_choice", "show_missing", "guessed",
               "confusion", "grading", "grade_failed", "grade_error", "grade_error_code", "priorities",
               "explanations", "explain_failed", "explain_errors", "notes", "notes_failed", "notices", "auto_done",
               "quick_diag", "q_mode"]


def clear_results() -> None:
    for k in RESULT_KEYS:
        v = DEFAULTS[k]
        st.session_state[k] = v.copy() if isinstance(v, (dict, list)) else v
    for k in list(st.session_state.keys()):
        if k.startswith(("ans_", "dk_", "mcq_", "guess_", "conf_", "w_")):
            del st.session_state[k]


def run_analysis(name: str, data: bytes, paste: str, audio, from_sample: bool) -> bool:
    """S01 분석 1~7단계. 성공하면 True(호출한 쪽에서 S02로 이동)."""
    st.session_state["errors"] = []
    if not take_analysis():
        return False
    ok = False
    try:
        with st.status("분석 중이에요", expanded=True) as status:
            status.write("텍스트 추출 중")
            material = extract(name, data)
            run_id = file_hash(data)
            notices = []
            if material.get("truncated"):
                notices.append("앞 120쪽만 분석해요. 한 장씩 올리면 더 정확해요 (E-13)")
            transcript, source = None, None
            if paste and paste.strip():
                transcript, source = mask(paste.strip()), "paste"  # 대본은 받자마자 가린다
            elif audio is not None:
                status.write("녹음 받아쓰는 중")
                try:
                    check_audio(audio.name, audio.size)
                    transcript, source = mask(stt.transcribe(audio.name, audio.getvalue())), "audio"
                except Exception:
                    notices.append("녹음을 글자로 바꾸지 못해 녹음 없이 계산했어요. 대본 붙여넣기로 다시 분석할 수 있어요 (E-05)")
            status.write("개념 찾는 중")
            sink: list = []
            cres = cached_concepts(run_id, _ver("concepts"), material, sink)
            concepts = cres["concepts"]
            meta = meta_pages(material["pages"], cres)
            utts = []
            if transcript:
                status.write("교수님 강조 찾는 중")
                import json as _json
                utts = cached_utterances(run_id, _ver("utterances"), transcript,
                                         _json.dumps(concepts, ensure_ascii=False, sort_keys=True), concepts, sink)
                if not utts:
                    notices.append("녹음에서 강조한 말을 찾지 못했어요. 자료만으로 점수를 계산했어요 (E-10)")
            status.write("점수 계산 중")
            scores = compute_scores(concepts, utts, meta)["scores"]
            for u in sink:
                add_usage(u)
            status.update(label="분석 완료", state="complete", expanded=False)
        clear_results()
        st.session_state.update({
            "material": material, "transcript": transcript, "transcript_source": source, "concepts": concepts,
            "concept_result": cres, "meta": meta, "utterances": utts, "scores": scores, "run_id": run_id,
            "from_sample": from_sample, "material_bytes": data if material["kind"] == "pdf" else None,
            "notices": notices, "step": 2,
        })
        ok = True
    except (ExtractError, NoConceptsError, LLMError) as e:
        code = getattr(e, "code", "E-08")
        st.session_state["errors"] = [f"{getattr(e, 'user_message', error_message(e))} ({code})", f"__detail__{e}"]
    except Exception as e:  # 잡히지 않은 예외
        st.session_state["errors"] = ["알 수 없는 오류가 났어요. 처음부터 다시 해 주세요", f"__detail__{type(e).__name__}: {e}"]
    finally:
        if not ok:
            give_back_analysis()
    return ok


# ---------- 공통 화면 ----------

STEP_NAMES = {1: "자료 올리기", 2: "출제 포인트", 3: "취약점 진단", 4: "공부 순서", 5: "안내·설정"}


def can_go(step: int) -> bool:
    s = st.session_state
    if step in (1, 5):
        return True
    if step in (2, 3):
        return s["scores"] is not None
    return s["priorities"] is not None


def sidebar() -> None:
    with st.sidebar:
        st.markdown("### 빈틈노트")
        for n in range(1, 6):
            label = f"{'①②③④⑤'[n - 1]} {STEP_NAMES[n]}"
            if st.button(label, key=f"nav_{n}", type="primary" if st.session_state["step"] == n else "secondary",
                         disabled=not can_go(n), width="stretch"):
                st.session_state["step"] = n
                st.rerun()
        st.divider()
        if st.button("처음부터", width="stretch"):
            reset_all()
            st.rerun()


def header() -> None:
    cur = st.session_state["step"]
    parts = []
    for n in range(1, 5):
        t = f"{'①②③④'[n - 1]} {STEP_NAMES[n]}"
        parts.append(f"<b>{t}</b>" if n == cur else t)
    H(f"<div class='bt-steps'>{' › '.join(parts)}</div>")
    st.title("빈틈노트")
    st.caption("강의자료와 교수님 녹음 속 강조점, 메타인지 진단으로 시험 전 공부 우선순위를 정해 주는 앱")


# ---------- S01 ----------

def s01() -> None:
    st.info(DISCLAIMER)
    if fake_mode():
        st.warning("가짜 AI 모드(BINTM_FAKE_AI=1)예요. 실제 AI 대신 저장된 답으로 화면만 보여 줘요.")
    key_ok = has_key()
    if not key_ok:
        st.error("AI 키가 설정되지 않았어요. README의 설정 방법을 보세요 (E-06)")
    st.caption(DATA_NOTE)

    up = st.file_uploader("강의자료 (PDF/PPTX, 최대 30MB)", type=["pdf", "pptx"], key="w_material",
                          max_upload_size=config.MAX_MATERIAL_MB)
    if up is not None:
        st.caption(f"올린 파일: {up.name} · {up.size / 1024 / 1024:.1f}MB")
    tab_audio, tab_paste = st.tabs(["녹음 파일", "대본 붙여넣기"])
    with tab_audio:
        st.caption("교수님 허락을 받은 녹음만, 개인 학습 목적으로만 올려 주세요.")
        if not stt.available():
            st.caption("음성 인식 키가 없어 녹음 파일은 쓸 수 없어요. 대본 붙여넣기를 써 주세요.")
        audio = st.file_uploader("녹음 (m4a/mp3/wav, 최대 25MB)", type=["m4a", "mp3", "wav"], key="w_audio",
                                 max_upload_size=config.MAX_AUDIO_MB, disabled=not stt.available())
    with tab_paste:
        st.caption("받아쓰기 앱(예: 휴대폰 녹음 앱의 받아쓰기)으로 만든 대본을 붙여 넣어도 돼요. 둘 다 있으면 대본이 우선이에요.")
        paste = st.text_area("강의 대본", key="w_paste", height=160,
                             placeholder="교수님 강의를 받아쓴 글을 붙여 넣어 주세요. 없어도 분석할 수 있어요.")

    c1, c2 = st.columns(2)
    start = c1.button("분석 시작", type="primary", disabled=(up is None or not key_ok), width="stretch")
    sample = c2.button("샘플로 체험", disabled=not key_ok, width="stretch",
                       help="직접 만든 가상 강의자료(자료구조 8장, 20쪽)와 대본으로 바로 써 봐요")
    left = session_left(st.session_state["analyses_used"], config.MAX_ANALYSES_PER_SESSION)
    if 0 <= left <= 2:
        st.caption(f"이 화면에서 분석은 {left}번 더 할 수 있어요.")

    moved = False
    if start and up is not None:
        try:
            from core.extract import check_material
            check_material(up.name, up.size)
            moved = run_analysis(up.name, up.getvalue(), paste, audio, False)
        except ExtractError as e:
            st.session_state["errors"] = [f"{e.user_message} ({e.code})"]
    if sample:
        moved = run_analysis(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes(), SAMPLE_TXT.read_text(encoding="utf-8"),
                             None, True)
    if moved:
        st.rerun()
    errs = st.session_state.get("errors") or []
    for e in errs:
        if e.startswith("__detail__"):
            with st.expander("자세한 오류"):
                st.code(e[len("__detail__"):][:1500])
        else:
            st.error(e)


# ---------- S02 ----------

def current_targets() -> list[str]:
    s = st.session_state
    quick = s["quick_diag"]
    if "w_quick" in s and not s["grading"]:
        quick = s["w_quick"]
    return diag_targets(s["scores"], top=config.QUICK_DIAG_TOP if quick else None)


def s02() -> None:
    s = st.session_state
    for n in s["notices"]:
        st.warning(n)
    scores = s["scores"]
    all_targets = diag_targets(scores)
    m1, m2, m3 = st.columns(3)
    m1.metric("찾은 개념", len(scores))
    m2.metric("교수님 강조", len([u for u in s["utterances"] if u.get("concept_id")]))
    m3.metric("진단할 개념", len(current_targets()))
    if not s["transcript"]:
        st.info("녹음 없이 자료만으로 계산했어요. 녹음을 넣으면 순위가 더 정확해져요")

    st.subheader("출제 포인트 순위")
    rows = []
    low = [r for r in scores if r["pct"] < config.DIAG_MIN_PCT]
    for r in scores:
        if low and r is low[0]:
            rows.append(f"<div class='info' style='margin-top:10px'>아래 {len(low)}개는 출제 가능성 점수가 "
                        f"{config.DIAG_MIN_PCT}점 미만이라 진단하지 않고 '복습만'으로 둬요</div>")
        bs = "".join(f'<span class="b{" minus" if minus else ""}">{esc(t)}</span>' for t, minus in badges(r))
        faded = " faded" if r["pct"] < config.DIAG_MIN_PCT else ""
        rows.append(f"<div class='bt-row{faded}'><b>{r['rank']}. {esc(r['name'])}</b> &nbsp;{bar(r['pct'])} "
                    f"<b>{r['pct']}점</b><br>{bs}</div>")
    H("".join(rows))
    st.caption(SCORE_NOTE)
    st.caption(DISCLAIMER)

    with st.expander("점수 내역과 교수님이 한 말 자세히 보기"):
        by_id = {c["id"]: c for c in s["concepts"]}
        parts = []
        for r in scores:
            c = by_id.get(r["concept_id"], {})
            reasons = "".join(f"<li>{esc(x['label'])}: {x['points']:+.2f}</li>" for x in r["reasons"]) or "<li>신호 없음</li>"
            quotes = "".join(f"<li>[{esc(TYPE_LABEL.get(u['type'], u['type']))}] “{esc(u['quote'])}”</li>"
                             for u in s["utterances"] if u.get("concept_id") == r["concept_id"])
            obj = f"<div class='info'>학습목표: {esc(c.get('objective_quote'))}</div>" if c.get("objective_quote") else ""
            parts.append(f"<div class='bt-row'><b>{r['rank']}. {esc(r['name'])}</b> · {r['pct']}점 (raw {r['raw']:.2f})"
                         f"<div>{esc(c.get('summary', ''))}</div><div class='info'>등장 페이지 "
                         f"{pages_badges(c.get('pages'))}</div>{obj}<ul>{reasons}</ul>"
                         f"{'<div><b>교수님이 한 말</b></div><ul>' + quotes + '</ul>' if quotes else ''}</div>")
        outside = [u for u in s["utterances"] if not u.get("concept_id")]
        if outside:
            parts.append("<div><b>개념 목록 밖 언급</b></div><ul>" + "".join(
                f"<li>{esc(u.get('concept_name'))}: “{esc(u['quote'])}”</li>" for u in outside) + "</ul>")
        H("".join(parts))

    st.subheader("진단 설정")
    graded = bool(s["grading"])
    if "w_q_mode" in s:
        st.radio("문제 형식", MODES, key="w_q_mode", horizontal=True, disabled=graded,
                 help="섞어서: 출제 점수 50점 이상은 서술형, 나머지는 객관식")
    else:
        st.radio("문제 형식", MODES, index=MODES.index(s["q_mode"]), key="w_q_mode", horizontal=True,
                 disabled=graded, help="섞어서: 출제 점수 50점 이상은 서술형, 나머지는 객관식")
    s["q_mode"] = s["w_q_mode"]
    if len(all_targets) > config.QUICK_DIAG_TOP:
        rest = len(all_targets) - config.QUICK_DIAG_TOP
        helptext = (f"{len(all_targets)}문제 대신 {config.QUICK_DIAG_TOP}문제만 풀어요. 나머지 {rest}개는 '진단 안 함'"
                    f"(이해도 0.5)으로 공부 순서를 계산해요.")
        kw = {} if "w_quick" in s else {"value": s["quick_diag"]}
        st.toggle(f"빠른 진단: 출제 가능성 상위 {config.QUICK_DIAG_TOP}개만 풀기", key="w_quick", disabled=graded,
                  help=helptext, **kw)
        if not graded:
            s["quick_diag"] = s["w_quick"]
    n = len(current_targets())
    if st.button(f"{n}개 개념 진단하기", type="primary", disabled=n == 0):
        s["step"] = 3
        st.rerun()
    if n == 0:
        st.info("출제 가능성 점수 20점 이상인 개념이 없어 진단할 문제가 없어요.")


# ---------- S03 ----------

def concept_by_id() -> dict:
    return {c["id"]: c for c in st.session_state["concepts"]}


def pct_of(cid: str) -> int:
    for r in st.session_state["scores"]:
        if r["concept_id"] == cid:
            return r["pct"]
    return 0


def ensure_questions() -> None:
    """대상 개념마다 고른 형식의 문제를 준비한다. 문제는 (개념, 형식)으로 보관한다."""
    s = st.session_state
    targets = current_targets()
    s["diag_ids"] = targets
    cby = concept_by_id()
    names = [cby[c]["name"] for c in targets]
    need = {}
    for cid in targets:
        kind = choose_kind(pct_of(cid), s["q_mode"])
        key = f"{cid}|{kind}"
        if key in s["qbank"] or key in s["q_failed_keys"]:
            continue
        need[key] = (cid, kind)
    if need and not s["grading"]:
        cache = sample_cache() if s["from_sample"] else None
        tasks = {}
        for key, (cid, kind) in need.items():
            ck = (s["run_id"], cid, kind, tuple(names))
            hit = cache.get(ck) if cache is not None else None
            if hit:
                s["qbank"][key] = hit  # 저장된 문제: AI 호출·사용량 없음
                continue
            pages = evidence_pages(cby[cid], s["material"], s["meta"])
            tasks[key] = (lambda u, c=cby[cid], k=kind, p=pages: make_question(c, k, p, names, u))
        if tasks:
            with st.spinner(f"진단 문제 {len(tasks)}개를 만드는 중이에요. 30초쯤 걸려요"):
                res, errs, usage = run_parallel(tasks, workers=6)
            add_usage(usage)
            for key, q in res.items():
                s["qbank"][key] = q
                if cache is not None:
                    cid, kind = need[key]
                    cache.put((s["run_id"], cid, kind, tuple(names)), q)
            for key, e in errs.items():
                s["q_failed_keys"][key] = f"{error_message(e)} ({error_code(e)})"
    qs, failed = {}, []
    for cid in targets:
        key = f"{cid}|{choose_kind(pct_of(cid), s['q_mode'])}"
        if key in s["qbank"]:
            qs[cid] = s["qbank"][key]
        elif key in s["q_failed_keys"]:
            failed.append(cby[cid]["name"])
    if not s["grading"]:
        s["questions"] = qs
    s["q_failed"] = failed


def widget_values(cid: str, q: dict) -> dict:
    """입력칸의 지금 값(아직 안 그려졌으면 세션 딕셔너리)."""
    s = st.session_state
    if q["kind"] == MCQ:
        choice = s.get(f"mcq_{cid}", s["mcq_choice"].get(cid))
        return {"choice": choice, "guessed": s.get(f"guess_{cid}", s["guessed"].get(cid, False)),
                "confusion": s.get(f"conf_{cid}", s["confusion"].get(cid, ""))}
    return {"answer": s.get(f"ans_{cid}", s["answers"].get(cid, "")),
            "dont_know": s.get(f"dk_{cid}", s["dont_know"].get(cid, False))}


def answered(cid: str, q: dict) -> bool:
    v = widget_values(cid, q)
    return is_answered(q, v.get("answer"), v.get("dont_know", False), v.get("choice"))


def fill_examples() -> None:
    """예시 답 채우기: 입력칸이 그려지기 전에 세션 키에 넣는다."""
    s = st.session_state
    ex = example_answers([(cid, s["questions"][cid]) for cid in s["diag_ids"] if cid in s["questions"]])
    for cid, a in ex.items():
        if "choice" in a:
            s[f"mcq_{cid}"] = a["choice"]
            s[f"guess_{cid}"] = a["guessed"]
            s[f"conf_{cid}"] = a["confusion"]
            s["mcq_choice"][cid] = a["choice"]
            s["guessed"][cid] = a["guessed"]
            s["confusion"][cid] = a["confusion"]
        else:
            s[f"ans_{cid}"] = a["answer"]
            s[f"dk_{cid}"] = a["dont_know"]
            s["answers"][cid] = a["answer"]
            s["dont_know"][cid] = a["dont_know"]
    s["show_missing"] = False


def answer_block(q: dict, g: dict, ans: dict, confusion: str = "") -> str:
    parts = []
    if q["kind"] == MCQ:
        ch = ans.get("choice")
        for i, c in enumerate(q["choices"]):
            cls, mark = "choice", ""
            if i == q["answer_index"]:
                cls += " right"
                mark = " ✔ 정답"
            if ch == i and i != q["answer_index"]:
                cls += " mine"
                mark = " ✘ 내 답"
            elif ch == i:
                mark += " · 내 답"
            parts.append(f"<div class='{cls}'>{CHOICE_MARKS[i]} {esc(c)}{esc(mark)}</div>")
        if ch == DONT_KNOW:
            parts.append("<div class='choice mine'>내 답: 모르겠어요</div>")
        if confusion:
            parts.append(f"<div class='conf'><b>💬 내가 헷갈린 점</b> {esc(confusion)}</div>")
        parts.append(f"<div style='margin-top:6px'><b>해설</b></div>{rich(q.get('explanation', ''))}")
    else:
        mine = "모르겠어요" if ans.get("dont_know") else (ans.get("answer") or "(빈 답)")
        parts.append(f"<div><b>내 답</b></div>{rich(mine)}")
    et = f" · {esc(g.get('error_type'))}" if g.get("error_type") else ""
    parts.append(f"<div>{status_badge(g['status'])}<b>{g['score']}/10</b>{et}</div>{rich(g.get('reason', ''))}")
    parts.append(f"<div class='info'>근거 페이지 {pages_badges(q.get('source_pages'))}</div>")
    return "".join(parts)


def essay_detail(q: dict, g: dict) -> str:
    rs = g.get("rubric_scores") or []
    items = "".join(f"<li>{esc(r['point'])} ({rs[i] if i < len(rs) else '-'}/{r['score']})</li>"
                    for i, r in enumerate(q.get("rubric", [])))
    return f"<div><b>모범 답안</b></div>{rich(q.get('answer', ''))}<div><b>루브릭</b></div><ul>{items}</ul>"


def grade_now(only: list[str] | None = None) -> None:
    """모든 문제에 답했으면 한 번에 채점. only를 주면 그 서술형만 다시 채점."""
    s = st.session_state
    cby = concept_by_id()
    ids = only or list(s["questions"].keys())
    tasks = {}
    for cid in ids:
        q = s["questions"][cid]
        if q["kind"] == MCQ:
            ch, gu = s["mcq_choice"].get(cid), s["guessed"].get(cid, False)
            s["grading"][cid] = local_grading(q, None, False, ch, gu)
            continue
        a, dk = s["answers"].get(cid, ""), s["dont_know"].get(cid, False)
        g = local_grading(q, a, dk, None, False)
        if g is not None:
            s["grading"][cid] = g
            continue
        pages = evidence_pages(cby[cid], s["material"], s["meta"])
        tasks[cid] = (lambda u, q=q, a=a, p=pages: grade_essay(q, a, p, u))
    failed, first_err = [], None
    if tasks:
        with st.spinner(f"서술형 {len(tasks)}문제를 채점하는 중이에요"):
            res, errs, usage = run_parallel(tasks, workers=6)
        add_usage(usage)
        for cid, g in res.items():
            s["grading"][cid] = g
        for cid, e in errs.items():
            failed.append(cid)
            s["grading"].pop(cid, None)
            first_err = first_err or e
    s["grade_failed"] = failed
    s["grade_error"] = f"{type(first_err).__name__}: {first_err}" if first_err else None
    s["grade_error_code"] = (error_message(first_err), error_code(first_err)) if first_err else None


def all_graded() -> bool:
    s = st.session_state
    return bool(s["questions"]) and all(cid in s["grading"] for cid in s["questions"]) and not s["grade_failed"]


def s03() -> None:
    s = st.session_state
    ensure_questions()
    cby = concept_by_id()
    if s["q_failed"]:
        codes = {v for v in s["q_failed_keys"].values()}
        st.warning(f"문제를 만들지 못해 진단에서 뺀 개념: {', '.join(s['q_failed'])} · " + " / ".join(codes))
        if not s["grading"] and st.button("만들지 못한 문제 다시 만들기"):
            s["q_failed_keys"] = {}
            st.rerun()
    order = [cid for cid in s["diag_ids"] if cid in s["questions"]]
    if not order:
        st.error("진단 문제를 하나도 만들지 못했어요. 잠시 후 다시 시도해 주세요")
        return
    graded = bool(s["grading"])
    qs = s["questions"]

    if s["grade_failed"]:
        msg, code = s["grade_error_code"] or ("AI 답을 읽지 못했어요. 다시 시도해 주세요", "E-08")
        st.error(f"서술형 {len(s['grade_failed'])}문제를 채점하지 못했어요. {msg} ({code})")
        with st.expander("자세한 오류"):
            st.code(s["grade_error"] or "")
    if all_graded():
        c = [sum(1 for g in s["grading"].values() if g["status"] == k) for k in ("앎", "헷갈림", "모름")]
        m1, m2, m3 = st.columns(3)
        m1.metric("앎", c[0])
        m2.metric("헷갈림", c[1])
        m3.metric("모름", c[2])

    n_done = sum(1 for cid in order if answered(cid, qs[cid]))
    n_mcq = sum(1 for cid in order if qs[cid]["kind"] == MCQ)
    st.progress(n_done / len(order), text=f"답한 문제 {n_done} / {len(order)} · 객관식 {n_mcq} · 서술형 {len(order) - n_mcq}")
    if s["from_sample"] and not graded and n_done < len(order):
        st.caption("샘플로 둘러보는 중이라면 '예시 답 채우기'로 바로 채점까지 가 볼 수 있어요.")
        if st.button("예시 답 채우기 (샘플 체험용)"):
            fill_examples()
            st.rerun()

    for i, cid in enumerate(order, 1):
        q = qs[cid]
        g = s["grading"].get(cid)
        with st.container(border=True):
            H(f"<div><b>Q{i}. {esc(cby[cid]['name'])}</b> <span class='b'>{esc(q['kind'])}</span>"
              f"<span class='b'>출제 점수 {pct_of(cid)}</span></div><div class='q-text'>{esc(q['question'])}</div>"
              f"{figure_html(q.get('figure'))}")
            locked = g is not None and cid not in s["grade_failed"]
            if q["kind"] == MCQ:
                opts = [0, 1, 2, 3, DONT_KNOW]
                labels = {o: (f"{CHOICE_MARKS[o]} {q['choices'][o]}" if o >= 0 else "모르겠어요") for o in opts}
                kw = {} if f"mcq_{cid}" in s else {"index": opts.index(s["mcq_choice"][cid]) if s["mcq_choice"].get(cid) in opts else None}
                ch = st.radio("보기", opts, key=f"mcq_{cid}", format_func=lambda o, L=labels: L[o],
                              label_visibility="collapsed", disabled=locked, **kw)
                s["mcq_choice"][cid] = ch
                if ch is not None and ch >= 0:
                    kw = {} if f"guess_{cid}" in s else {"value": s["guessed"].get(cid, False)}
                    gu = st.checkbox("확신 없이 골랐어요 (찍었어요)", key=f"guess_{cid}", disabled=locked, **kw)
                    s["guessed"][cid] = gu
                    if gu:
                        kw = {} if f"conf_{cid}" in s else {"value": s["confusion"].get(cid, "")}
                        conf = st.text_area("어떤 점이 헷갈렸나요? (선택)", key=f"conf_{cid}", disabled=locked,
                                            max_chars=config.CONFUSION_MAX_CHARS, height=80,
                                            placeholder="②와 ③ 중에 고민했어요. 두 방법이 어떻게 다른지 모르겠어요.", **kw)
                        s["confusion"][cid] = conf
                    else:
                        s["confusion"][cid] = ""
                else:
                    s["guessed"][cid] = False
                    s["confusion"][cid] = ""
            else:
                kw = {} if f"ans_{cid}" in s else {"value": s["answers"].get(cid, "")}
                a = st.text_area("답", key=f"ans_{cid}", disabled=locked, height=110, label_visibility="collapsed",
                                 placeholder="아는 만큼 2~3문장으로 적어 주세요.", **kw)
                s["answers"][cid] = a
                kw = {} if f"dk_{cid}" in s else {"value": s["dont_know"].get(cid, False)}
                dk = st.checkbox("모르겠어요", key=f"dk_{cid}", disabled=locked, **kw)
                s["dont_know"][cid] = dk
            if s["show_missing"] and not graded and not answered(cid, q):
                H("<div class='missing'>아직 답하지 않았어요. 모르면 '모르겠어요'를 골라 주세요.</div>")
            if cid in s["grade_failed"]:
                H("<div class='missing'>이 문제는 채점하지 못했어요. 답은 그대로 남아 있어요.</div>")
            if g is not None:
                ans = {"choice": s["mcq_choice"].get(cid), "answer": s["answers"].get(cid, ""),
                       "dont_know": s["dont_know"].get(cid, False)}
                conf = s["confusion"].get(cid, "") if q["kind"] == MCQ and s["guessed"].get(cid) else ""
                H(answer_block(q, g, ans, conf))
                if q["kind"] == ESSAY:
                    with st.expander("모범 답안과 루브릭 보기"):
                        H(essay_detail(q, g))

    if not graded:
        st.caption("모든 문제에 답해야 채점해요. 모르면 '모르겠어요'를 고르면 돼요.")
        if st.button("채점하기", type="primary"):
            missing = [f"Q{i}" for i, cid in enumerate(order, 1) if not answered(cid, qs[cid])]
            if missing:
                s["show_missing"] = True
                s["missing_list"] = missing
                st.rerun()
            else:
                s["show_missing"] = False
                grade_now()
                st.rerun()
        if s["show_missing"] and s.get("missing_list"):
            st.error(f"아직 답하지 않은 문제: {', '.join(s['missing_list'])} (E-11)")
    elif s["grade_failed"]:
        c1, c2 = st.columns(2)
        if c1.button("채점 못한 문제 다시 채점", type="primary"):
            grade_now(only=list(s["grade_failed"]))
            st.rerun()
        if c2.button("채점 못한 문제는 빼고 공부 순서 보기"):
            for cid in s["grade_failed"]:
                s["questions"].pop(cid, None)
            s["grade_failed"] = []
            go_s04()
    else:
        if st.button("공부 순서 보기", type="primary"):
            go_s04()


def go_s04() -> None:
    s = st.session_state
    s["priorities"] = compute_priorities(s["scores"], s["grading"])
    s["auto_done"] = False
    s["step"] = 4
    st.rerun()


# ---------- S04 ----------

def answer_info(cid: str) -> dict:
    s = st.session_state
    return {"answer": s["answers"].get(cid, ""), "dont_know": s["dont_know"].get(cid, False),
            "choice": s["mcq_choice"].get(cid), "guessed": s["guessed"].get(cid, False)}


def written_confusion(cid: str) -> str:
    s = st.session_state
    q = s["questions"].get(cid)
    if q and q["kind"] == MCQ and s["guessed"].get(cid):
        return clean_confusion(s["confusion"].get(cid, ""))
    return ""


def explain_task(cid: str):
    s = st.session_state
    c = concept_by_id()[cid]
    pages = evidence_pages(c, s["material"], s["meta"])
    q, g = s["questions"].get(cid), s["grading"].get(cid)
    ans, conf = answer_info(cid), written_confusion(cid)
    return lambda u: make_explanation(c, q if g else None, g, ans, conf, pages, u)


def note_task(cid: str, detail: str):
    s = st.session_state
    c = concept_by_id()[cid]
    pages = evidence_pages(c, s["material"], s["meta"])
    prio = next(p for p in s["priorities"] if p["concept_id"] == cid)
    g = s["grading"].get(cid)
    utts = list(s["utterances"])  # 스레드 안에서 세션을 읽지 않게 밖에서 꺼낸다
    return lambda u: make_note(c, detail, prio, g, utts, pages, u)


def note_details() -> dict:
    s = st.session_state
    return {p["concept_id"]: detail_level(p["action"], p["exam_pct"], p["status"]) for p in s["priorities"]}


def run_batch(explain_ids: list[str], note_ids: list[str], label: str) -> None:
    """보완 설명과 요약 노트를 한 번에 8개씩 동시에. 실패는 표시만 하고 자동으로 다시 부르지 않는다."""
    s = st.session_state
    details = note_details()
    tasks = {}
    for cid in explain_ids:
        tasks[("ex", cid)] = explain_task(cid)
    for cid in note_ids:
        tasks[("note", cid)] = note_task(cid, details[cid])
    if not tasks:
        return
    with st.spinner(label):
        res, errs, usage = run_parallel(tasks, workers=8)
    add_usage(usage)
    for (kind, cid), v in res.items():
        if kind == "ex":
            s["explanations"][cid] = v
            if cid in s["explain_failed"]:
                s["explain_failed"].remove(cid)
        else:
            s["notes"][cid] = v
            if cid in s["notes_failed"]:
                s["notes_failed"].remove(cid)
    for (kind, cid), e in errs.items():
        lst = s["explain_failed"] if kind == "ex" else s["notes_failed"]
        if cid not in lst:
            lst.append(cid)
        s["explain_errors"][f"{kind}:{cid}"] = f"{error_message(e)} ({error_code(e)}) · {type(e).__name__}: {e}"[:600]


def auto_generate() -> None:
    s = st.session_state
    if s["auto_done"]:
        return
    pr = s["priorities"]
    ex_ids = [p["concept_id"] for p in pr if p["action"] == "지금 당장"]
    ex_ids += [p["concept_id"] for p in pr[: config.AUTO_EXPLAIN_TOP]]
    ex_ids += [cid for cid in s["questions"] if written_confusion(cid)]
    ex_ids = [c for i, c in enumerate(ex_ids) if c not in ex_ids[:i] and c not in s["explanations"]]
    details = note_details()
    for cid, d in details.items():
        if d == "짧게" and cid not in s["notes"]:
            s["notes"][cid] = short_note(concept_by_id()[cid])
    note_ids = [cid for cid, d in details.items() if d != "짧게" and cid not in s["notes"]]
    s["auto_done"] = True
    run_batch(ex_ids, note_ids, f"보완 설명 {len(ex_ids)}개와 요약 노트 {len(note_ids)}개를 만드는 중이에요. 30초쯤 걸려요")


def export_state() -> dict:
    s = st.session_state
    keys = ["priorities", "scores", "questions", "grading", "answers", "dont_know", "mcq_choice", "guessed",
            "confusion", "explanations", "notes", "concepts", "meta", "utterances", "transcript_source"]
    d = {k: s[k] for k in keys}
    d["confusion"] = {cid: written_confusion(cid) for cid in s["questions"]}
    d["material_name"] = s["material"]["name"]
    d["date"] = _dt.date.today().isoformat()
    return d


def download_buttons(where: str) -> None:
    d = export_state()
    today = _dt.date.today().strftime("%Y%m%d")
    c1, c2 = st.columns(2)
    c1.download_button("📥 공부 순서·오답노트 내려받기", study_html(d).encode("utf-8"),
                       file_name=f"빈틈노트_공부순서_오답노트_{today}.html", mime="text/html",
                       key=f"dl_study_{where}", width="stretch")
    c2.download_button("📒 요약 노트 내려받기", notes_html(d).encode("utf-8"),
                       file_name=f"빈틈노트_요약노트_{today}.html", mime="text/html",
                       key=f"dl_notes_{where}", width="stretch")


def page_images(pages: list[int], key: str) -> None:
    s = st.session_state
    if not s["material_bytes"] or not pages:
        return
    shown = list(pages)[:2]
    with st.expander("강의자료 원본 보기 · " + ", ".join(f"p.{p}" for p in shown)):
        for p in shown:
            img = cached_page_img(s["run_id"], int(p), s["material_bytes"])
            if img:
                st.image(img, caption=f"p.{p}")


def confusion_html(written: str, reply: str | None) -> str:
    if not written:
        return ""
    if reply:
        return (f"<div class='conf'><b>💬 내가 헷갈린 점에 대한 답</b><div class='info'>내가 적은 글: {esc(written)}</div>"
                f"{rich(reply)}</div>")
    return f"<div class='conf'><b>💬 내가 헷갈린 점</b> {esc(written)}</div>"


def study_card(p: dict) -> None:
    s = st.session_state
    cid = p["concept_id"]
    q, g = s["questions"].get(cid), s["grading"].get(cid)
    ex = s["explanations"].get(cid)
    with st.container(border=True):
        H(f"<div><b>{p['rank']}. {esc(p['name'])}</b></div>{status_badge(p['status'])}"
          f"<span class='b'>출제 점수 {p['exam_pct']}</span><span class='b'>우선순위 {p['priority']}</span>")
        if q and g:
            with st.expander(f"📝 내 문제와 답 다시 보기 · {g['status']} {g['score']}/10"):
                conf = written_confusion(cid)
                H(f"<div class='q-text'>{esc(q['question'])}</div>{figure_html(q.get('figure'))}"
                  + answer_block(q, g, answer_info(cid), conf if not (ex and ex.get('confusion_reply')) else ""))
                if q["kind"] == ESSAY:
                    H(essay_detail(q, g))
        if ex:
            parts = []
            if ex.get("my_gap"):
                parts.append(f"<div class='gap'><b>내가 놓친 점</b> {esc(ex['my_gap'])}</div>")
            parts.append(confusion_html(written_confusion(cid), ex.get("confusion_reply")))
            parts.append(rich(ex.get("explanation", "")))
            if ex.get("not_found"):
                parts.append(f"<div class='nf'>올린 자료에서 찾지 못함 · {esc(ex.get('not_found_note') or '')} "
                             f"교재 다른 장이나 수업 노트를 확인하세요.</div>")
            parts.append(f"<div class='info'>다시 볼 페이지 {pages_badges(ex.get('check_pages'))}</div>")
            H("".join(parts))
            page_images(ex.get("check_pages") or ex.get("source_pages"), f"ex_{cid}")
        elif cid in s["explain_failed"]:
            err = s["explain_errors"].get(f"ex:{cid}", "")
            H(f"<div class='missing'>설명을 만들지 못했어요. {esc(err.split(' · ')[0])}</div>")
            if st.button("설명 다시 만들기", key=f"reex_{cid}"):
                run_batch([cid], [], "설명을 다시 만드는 중이에요")
                st.rerun()
        else:
            if st.button("설명 보기", key=f"ex_{cid}"):
                run_batch([cid], [], "설명을 만드는 중이에요")
                st.rerun()


def note_card(i: int, cid: str) -> None:
    s = st.session_state
    c = concept_by_id()[cid]
    n = s["notes"].get(cid)
    p = next((x for x in s["priorities"] if x["concept_id"] == cid), {})
    with st.container(border=True):
        detail = n["detail"] if n else note_details().get(cid, "")
        H(f"<div><b>{i}. {esc(c['name'])}</b> <span class='b'>{esc(detail)}</span></div>"
          f"{status_badge(p.get('status', ''))}<span class='b'>출제 점수 {p.get('exam_pct', 0)}</span>"
          f"<span class='b'>{esc(p.get('action', ''))}</span>")
        if n:
            parts = [rich(n.get("summary", ""))]
            if n.get("key_points"):
                parts.append("<div><b>핵심</b></div><ul>" + "".join(f"<li>{rich(k)[3:-4]}</li>" for k in n["key_points"]) + "</ul>")
            if n.get("pitfalls"):
                parts.append("<div><b>자주 하는 실수</b></div><ul>" + "".join(f"<li>{rich(k)[3:-4]}</li>" for k in n["pitfalls"]) + "</ul>")
            qs = professor_quotes(cid, s["utterances"], 3)
            if qs and n["detail"] != "짧게":
                parts.append("<div><b>교수님 말</b></div><ul>" + "".join(f"<li>“{esc(u['quote'])}”</li>" for u in qs) + "</ul>")
            parts.append(f"<div class='info'>근거 페이지 {pages_badges(n.get('source_pages'))}</div>")
            H("".join(parts))
            if n["detail"] != "짧게":
                page_images(n.get("source_pages"), f"note_{cid}")
        elif cid in s["notes_failed"]:
            err = s["explain_errors"].get(f"note:{cid}", "")
            H(f"<div class='missing'>요약 노트를 만들지 못했어요. {esc(err.split(' · ')[0])}</div>")
            if st.button("요약 노트 다시 만들기", key=f"renote_{cid}"):
                run_batch([], [cid], "요약 노트를 다시 만드는 중이에요")
                st.rerun()


def s04() -> None:
    s = st.session_state
    auto_generate()
    pr = s["priorities"]
    m = [sum(1 for p in pr if p["action"] == a) for a in ACTIONS]
    c1, c2, c3 = st.columns(3)
    c1.metric("지금 당장", m[0])
    c2.metric("다음", m[1])
    c3.metric("복습만", m[2])
    download_buttons("top")
    tab1, tab2 = st.tabs(["🎯 공부 순서와 오답노트", "📒 시험 대비 요약 노트"])
    with tab1:
        for a in ACTIONS:
            rows = [p for p in pr if p["action"] == a]
            if not rows:
                continue
            st.subheader(f"{a} · {len(rows)}개")
            st.caption(ACTION_DESC[a])
            if a == "다음":
                missing = [p["concept_id"] for p in rows if p["concept_id"] not in s["explanations"]
                           and p["concept_id"] not in s["explain_failed"]]
                if missing and st.button(f"'다음' 개념 설명 {len(missing)}개 한 번에 보기"):
                    run_batch(missing, [], f"설명 {len(missing)}개를 만드는 중이에요")
                    st.rerun()
            if a == "복습만":
                opened, folded = split_review(rows, [cid for cid in s["questions"] if written_confusion(cid)])
                for p in opened:
                    study_card(p)
                if folded:
                    with st.expander(f"복습만 {len(folded)}개 펼치기"):
                        st.caption("'진단 안 함'은 출제 가능성 점수가 20점 미만이라 문제를 내지 않은 개념이에요.")
                        for p in folded:
                            study_card(p)
            else:
                for p in rows:
                    study_card(p)
        with st.expander("전체 표로 보기"):
            head = "<tr><th>순위</th><th>개념</th><th>출제 점수</th><th>이해 상태</th><th>우선순위</th><th>권장</th></tr>"
            body = "".join(f"<tr><td>{p['rank']}</td><td>{esc(p['name'])}</td><td>{bar(p['exam_pct'])} {p['exam_pct']}점</td>"
                           f"<td>{status_badge(p['status'])}</td><td>{bar(p['priority'])} {p['priority']}</td>"
                           f"<td>{esc(p['action'])}</td></tr>" for p in pr)
            H(f"<div style='overflow-x:auto'><table style='border-collapse:collapse;width:100%;font-size:.92em'>"
              f"{head}{body}</table></div><div class='info'>우선순위 = 출제 점수 × (1 − 이해도). "
              f"이해도: 앎 1.0 · 헷갈림 0.5 · 모름 0.0 · 진단 안 함 0.5</div>")
    with tab2:
        st.caption("강의 순서대로 모든 개념을 정리했어요. 중요한 개념일수록 자세히 써요.")
        for i, cid in enumerate(lecture_order(s["concepts"], s["meta"]), 1):
            note_card(i, cid)
    st.divider()
    download_buttons("bottom")
    if st.button("다른 자료로 다시"):
        reset_all()
        st.rerun()


# ---------- S05 ----------

def s05() -> None:
    s = st.session_state
    st.subheader("사용 방법")
    st.markdown("1. ① 강의자료(PDF/PPTX)와 녹음 또는 대본을 올리고 분석을 시작해요. 파일이 없으면 '샘플로 체험'.\n"
                "2. ② 출제 가능성 점수 순위와 근거를 봐요.\n"
                "3. ③ 출제 점수 20점 이상 개념의 진단 문제를 풀어요. 찍은 문제는 '확신 없이 골랐어요'.\n"
                "4. ④ 공부 순서·오답노트와 시험 대비 요약 노트를 보고 내려받아요.")
    st.subheader("주의")
    st.markdown(f"- {DISCLAIMER}\n- 녹음은 교수님 허락을 받은 것만, 개인 학습 목적으로만 올려 주세요.\n- {DATA_NOTE}\n"
                f"- 배포 앱은 키 하나를 함께 쓰므로 분석은 화면 하나에서 {config.MAX_ANALYSES_PER_SESSION}번, "
                f"서버 전체 하루 {config.MAX_ANALYSES_PER_DAY}번까지예요.")
    st.subheader("현재 설정")
    u = s["usage"]
    rows = [("언어 모델", config.LLM_MODEL), ("음성 인식", "사용 가능" if stt.available() else "키 없음(대본 붙여넣기만)"),
            ("진단 기준", f"출제 가능성 점수 {config.DIAG_MIN_PCT}점 이상 전부"), ("문제 형식", s["q_mode"]),
            ("가중치 버전", config.WEIGHTS_VERSION),
            ("이번 세션 사용량", f"AI 호출 {u.calls}번 · 입력 {u.input_tokens:,} · 출력 {u.output_tokens:,} 토큰"),
            ("분석 횟수", f"{s['analyses_used']} / {config.MAX_ANALYSES_PER_SESSION}")]
    H("<table style='border-collapse:collapse'>" + "".join(
        f"<tr><td style='padding:4px 12px 4px 0;color:#64748b'>{esc(k)}</td><td>{esc(v)}</td></tr>" for k, v in rows) + "</table>")
    st.caption("AI 호출 수는 호출마다 세요. 저장된 결과를 다시 쓰면 AI를 부르지 않았으므로 더하지 않아요.")
    st.subheader("정보")
    st.markdown(f"- 팀: {config.TEAM_NAME}\n- 대회: {config.EVENT_NAME}\n- 저장소: {config.REPO_URL}")


# ---------- 시작 ----------

load_keys()
init_state()
H(CSS)
sidebar()
header()
step = st.session_state["step"]
if step in (2, 3) and st.session_state["scores"] is None or step == 4 and st.session_state["priorities"] is None:
    st.session_state["step"] = step = 1
    st.info("새로고침하면 결과가 사라져요. 결과는 ④에서 내보내기로 저장할 수 있어요 (E-14)")
try:
    {1: s01, 2: s02, 3: s03, 4: s04, 5: s05}[step]()
except KeyMissingError as e:
    show_error(e)
except LLMError as e:
    show_error(e)
