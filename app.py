# 빈틈노트 화면 S01~S05와 사이드바. 계산은 core/에 있고 이 파일은 화면만 다룬다.
import datetime as dt
import hashlib
import os
import sys
import threading
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent


# ---- 재배포 뒤 예전 모듈·프롬프트 버리기 (12장, v1.6·v1.9). core·config를 import하기 전에 둔다 ----
def watched_files() -> dict:
    files = [ROOT / "config.py"] + sorted((ROOT / "core").glob("*.py")) + sorted((ROOT / "prompts").glob("*.md"))
    return {str(p): p.stat().st_mtime for p in files if p.exists()}


def needs_reload(old, now: dict) -> bool:
    """기록이 없거나, 시각이 바뀌었거나, 기록에 없는 파일(프롬프트 포함)이 있으면 True."""
    if old is None:
        return True
    return any(k not in old or old[k] != v for k, v in now.items())


def _drop_stale_modules() -> None:
    now = watched_files()
    if needs_reload(getattr(sys, "_bintm_mtimes", None), now):
        for name in list(sys.modules):
            if name == "config" or name == "core" or name.startswith("core."):
                del sys.modules[name]
        st.cache_resource.clear()
    sys._bintm_mtimes = now


_drop_stale_modules()

import config  # noqa: E402
from core import concepts as concepts_mod  # noqa: E402
from core import diagnose, explain, export, note, priority, score, stt, utterances  # noqa: E402
from core.concepts import NoConceptsError  # noqa: E402
from core.diagnose import CHOICE_MARKS, ESSAY, MCQ, Q_MODES  # noqa: E402
from core.extract import ExtractError, extract, mask, run_id  # noqa: E402
from core.guard import DailyCounter, ResultCache, session_left  # noqa: E402
from core.llm import BadJSONError, LLMError, NoKeyError, Usage, has_key, is_fake  # noqa: E402
from core.pageimg import page_jpeg  # noqa: E402

SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다."
DATA_NOTICE = ("올린 자료와 녹음은 분석을 위해 AI 제공사(Anthropic, OpenAI) 서버로 전송됩니다. "
               "올린 파일은 서버 디스크에 저장하지 않아요. 결과는 이 브라우저 탭의 세션에 두고, "
               "같은 파일의 개념·강조 분석 결과와 쪽 그림만 서버 메모리 캐시에 잠시 둡니다(서버가 다시 켜지면 사라짐).")

ERR = {
    "E-01": "PDF나 PPTX만 올릴 수 있어요. 한글(hwp)은 파일 → PDF로 저장해 주세요",
    "E-02": "파일이 너무 커요(최대 30MB). 한 장만 따로 저장해 올려 주세요",
    "E-03": "이 PDF는 글자가 그림으로 들어 있어 읽을 수 없어요. 글자가 선택되는 PDF를 올려 주세요",
    "E-04": "녹음은 m4a/mp3/wav 25MB까지예요. 길면 앞부분만 잘라 올리거나 대본 붙여넣기를 써 주세요",
    "E-05": "녹음을 글자로 바꾸지 못했어요. 대본 붙여넣기를 쓰거나, 녹음 없이 계속할 수 있어요",
    "E-06": "AI 키가 설정되지 않았어요. README의 설정 방법을 보세요",
    "E-07": "AI 서버와 연결이 어려워요. 잠시 후 다시 시도 버튼을 눌러 주세요",
    "E-08": "AI 답을 읽지 못했어요. 다시 시도해 주세요",
    "E-09": "이 자료에서 개념을 찾지 못했어요. 강의 슬라이드나 교재 한 장인지 확인해 주세요",
    "E-10": "녹음에서 강조한 말을 찾지 못했어요. 자료만으로 점수를 계산했어요",
    "E-11": "아직 답하지 않았어요. 모르면 '모르겠어요'를 골라 주세요.",
    "E-13": "앞 120쪽만 분석해요. 한 장씩 올리면 더 정확해요",
    "E-16": "이 화면에서는 분석을 5번까지 할 수 있어요. 지금 결과는 ②~④에서 계속 볼 수 있어요.",
    "E-17": ("오늘 이 앱에서 쓸 수 있는 분석 횟수를 다 썼어요. 내일 다시 이용해 주세요. "
             "직접 실행하려면 README의 로컬 실행 방법을 보세요."),
    "UNKNOWN": "알 수 없는 오류가 났어요. 처음부터 다시 해 주세요",
}
STEPS = ["① 자료 올리기", "② 출제 포인트", "③ 취약점 진단", "④ 공부 순서", "⑤ 안내·설정"]

CSS = """
<style>
.block-container{max-width:860px;padding-top:2.2rem}
html,body,[data-testid="stMarkdownContainer"] p,[data-testid="stMarkdownContainer"] li{font-size:17px;line-height:1.75}
.bt p{margin:0 0 .6em}
.badge{display:inline-block;padding:1px 9px;border-radius:999px;font-size:.82em;margin:2px 4px 2px 0;
 background:#eef2f7;color:#1f2937;border:1px solid #d6dde6}
.ok{background:#dcfce7;color:#14532d;border-color:#86efac}.mid{background:#fef9c3;color:#713f12;border-color:#fde047}
.bad{background:#fee2e2;color:#7f1d1d;border-color:#fca5a5}.none{background:#f3f4f6;color:#374151}
.pg{display:inline-block;padding:0 6px;border-radius:6px;font-size:.82em;background:#dbeafe;color:#1e3a8a}
.bar{height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden;margin:4px 0}.bar i{display:block;height:8px;background:#2563eb}
.dim{opacity:.5}.gap{border-left:4px solid #dc2626;padding:6px 12px;margin:10px 0}
.conf{border-left:4px solid #2563eb;padding:6px 12px;margin:10px 0}
.nf{border:1px solid #ca8a04;background:#fef9c3;color:#713f12;padding:6px 12px;border-radius:8px;margin:10px 0}
ol.choices{padding-left:0;list-style:none}ol.choices li{padding:4px 8px;border-radius:6px;margin:2px 0}
.q{font-weight:600;font-size:1.05em}.muted{opacity:.7;font-size:.92em}.red{color:#dc2626;font-weight:600}
.stepline{font-size:.95em;opacity:.85;margin-bottom:.3rem}.stepline b{color:#2563eb}
.rankrow{border-bottom:1px solid rgba(128,128,128,.25);padding:6px 0}
.card h3{margin:0}.card{margin:0}
.tbl{border-collapse:collapse;width:100%}.tbl td,.tbl th{border:1px solid rgba(128,128,128,.3);padding:4px 8px;font-size:.92em;text-align:left;vertical-align:top}
[data-testid="stSpinner"]{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:10000;
 background:#ffffff;color:#111827;border:1px solid #cbd5e1;border-radius:12px;padding:10px 18px;
 box-shadow:0 6px 24px rgba(0,0,0,.18);width:auto;max-width:90vw}
[data-testid="stSpinner"] *{color:#111827}
@media (max-width:640px){html,body{font-size:16px}.block-container{padding-left:16px;padding-right:16px}}
</style>
"""


# ---- 서버 공용 자원 ----
@st.cache_resource
def daily_counter() -> DailyCounter:
    return DailyCounter(config.MAX_ANALYSES_PER_DAY)


@st.cache_resource
def sample_cache() -> ResultCache:
    return ResultCache(max_items=200)


_fresh = threading.local()


@st.cache_data(show_spinner=False, max_entries=50)
def cached_concepts(rid: str, _material: dict):
    _fresh.ran = True
    u = Usage()
    return concepts_mod.extract_concepts(_material, u), u


@st.cache_data(show_spinner=False, max_entries=50)
def cached_utterances(rid: str, transcript_hash: str, _concepts: list, _transcript: str):
    _fresh.ran = True
    u = Usage()
    return utterances.find_utterances(_concepts, _transcript, u), u


@st.cache_data(show_spinner=False, max_entries=200)
def cached_page_jpeg(rid: str, n: int, _data: bytes):
    return page_jpeg(_data, n)


def load_secrets() -> None:
    """st.secrets → 환경변수 순으로 찾는다."""
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        try:
            v = st.secrets.get(k)
        except Exception:
            v = None
        if v:
            os.environ[k] = str(v)


# ---- 세션 상태 (4.3) ----
def defaults() -> dict:
    return {
        "step": 1, "material": None, "transcript": None, "transcript_source": None, "concepts": None,
        "meta_pages": [], "utterances": [], "scores": None, "q_mode": "섞어서", "quick_diag": False,
        "diag_ids": [], "questions": {}, "answers": {}, "dont_know": {}, "mcq_choice": {}, "show_missing": False,
        "guessed": {}, "confusion": {}, "grading": {}, "grade_failed": [], "grade_error": None, "grade_skip": False,
        "q_failed": [], "q_error": None, "q_attempted": [], "priorities": None, "explanations": {},
        "explain_failed": [], "notes": {}, "notes_failed": [], "s04_attempted": [], "material_bytes": None,
        "model_name": config.LLM_MODEL, "run_id": None, "from_sample": False, "usage": Usage(), "errors": [],
        "missing_list": [],
    }


def init_state() -> None:
    for k, v in defaults().items():
        if k not in st.session_state:
            st.session_state[k] = v
    if "analyses_used" not in st.session_state:
        st.session_state.analyses_used = 0


def reset_all() -> None:
    """'다른 자료로 다시': 분석 횟수만 남기고 전부 지운다."""
    used = st.session_state.get("analyses_used", 0)
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state.analyses_used = used
    init_state()


def clear_after_analysis() -> None:
    d = defaults()
    for k in ("questions", "answers", "dont_know", "mcq_choice", "show_missing", "guessed", "confusion", "grading",
              "grade_failed", "grade_error", "grade_skip", "q_failed", "q_error", "q_attempted", "priorities",
              "explanations", "explain_failed", "notes", "notes_failed", "s04_attempted", "diag_ids", "missing_list"):
        st.session_state[k] = d[k]
    for k in list(st.session_state.keys()):
        if isinstance(k, str) and k.split("_")[0] in ("ans", "dk", "mcq", "guess", "conf"):
            del st.session_state[k]


ss = None  # main()에서 st.session_state로 채움


def H(html: str) -> None:
    st.html(f'<div class="bt">{html}</div>')


def show_error(code: str, detail=None) -> None:
    st.error(ERR.get(code, ERR["UNKNOWN"]))
    if detail:
        with st.expander("자세한 오류"):
            st.code(f"{type(detail).__name__}: {detail}" if isinstance(detail, Exception) else str(detail))


def error_code(e: Exception) -> str:
    return getattr(e, "code", "UNKNOWN")


# ---- 공통 계산 ----
def concept_by_id() -> dict:
    return {c["id"]: c for c in ss.concepts or []}


def pct_by_id() -> dict:
    return {s["concept_id"]: s["pct"] for s in ss.scores or []}


def all_targets() -> list[str]:
    return diagnose.diag_targets(ss.scores or [])


def current_targets() -> list[str]:
    return diagnose.diag_targets(ss.scores or [], top=config.QUICK_DIAG_TOP if ss.quick_diag else None)


def shown_questions() -> list[str]:
    return [cid for cid in ss.diag_ids if cid in ss.questions]


def graded_done() -> bool:
    qs = shown_questions()
    if not qs:
        return False
    pending = [c for c in qs if c not in ss.grading]
    return not pending or (ss.grade_skip and set(pending) <= set(ss.grade_failed))


def can_open(step: int) -> bool:
    if step in (1, 5):
        return True
    if step in (2, 3):
        return bool(ss.scores)
    if step == 4:
        return bool(ss.scores) and graded_done()
    return False


def go(step: int) -> None:
    ss.step = step


# ---- 사이드바와 머리 ----
def sidebar() -> None:
    with st.sidebar:
        st.markdown("### 빈틈노트")
        for i, label in enumerate(STEPS, start=1):
            st.button(label, key=f"nav_{i}", width="stretch",
                      type="primary" if ss.step == i else "secondary",
                      disabled=not can_open(i), on_click=go, args=(i,))
        st.divider()
        st.button("처음부터", key="nav_reset", width="stretch", on_click=reset_all)
        st.caption(DISCLAIMER)


def header(title: str, desc: str) -> None:
    parts = []
    for i, label in enumerate(STEPS[:4], start=1):
        parts.append(f"<b>{label}</b>" if ss.step == i else label)
    H(f'<div class="stepline">{" › ".join(parts)}</div>')
    st.title(title)
    st.write(desc)


def status_badge(status: str) -> str:
    return export.status_badge(status)


# ---- S01 ----
def take_analysis():
    """분석 1번을 쓴다. (성공 여부, 에러 코드)"""
    if session_left(ss.analyses_used, config.MAX_ANALYSES_PER_SESSION) == 0:
        return False, "E-16"
    if not daily_counter().try_take():
        return False, "E-17"
    ss.analyses_used += 1
    return True, None


def give_back_analysis() -> None:
    ss.analyses_used = max(0, ss.analyses_used - 1)
    daily_counter().give_back()


def run_analysis(data: bytes, name: str, paste_text: str, audio, from_sample: bool) -> None:
    ok, code = take_analysis()
    if not ok:
        show_error(code)
        return
    done = False
    usage = Usage()
    try:
        with st.status("분석하는 중이에요…", expanded=True) as status:
            status.write("텍스트 추출 중")
            material = extract(data, name)
            if material.get("truncated"):
                st.info(ERR["E-13"])
            transcript, source = None, None
            if paste_text and paste_text.strip():
                transcript, source = mask(paste_text.strip()), "paste"  # 대본은 받자마자 가린다
            elif audio is not None:
                status.write("녹음 받아쓰는 중")
                try:
                    from core.extract import check_audio
                    check_audio(audio.name, audio.size)
                    transcript, source = mask(stt.transcribe(audio.getvalue(), audio.name)), "audio"
                except ExtractError:
                    st.warning(ERR["E-04"])
                except stt.STTError as e:
                    st.warning(ERR["E-05"])
                    with st.expander("자세한 오류"):
                        st.code(str(e))
            rid = run_id(data)
            status.write("개념 찾는 중")
            _fresh.ran = False
            cres, u = cached_concepts(rid, material)
            if _fresh.ran:
                usage.merge(u)
            meta = concepts_mod.meta_pages(material, cres)
            utts = []
            if transcript:
                status.write("교수님 강조 찾는 중")
                _fresh.ran = False
                th = hashlib.sha256(transcript.encode("utf-8")).hexdigest()[:12]
                utts, u = cached_utterances(rid, th, cres["concepts"], transcript)
                if _fresh.ran:
                    usage.merge(u)
            status.write("점수 계산 중")
            scores = score.compute_scores(cres["concepts"], utts, meta)["scores"]
            status.update(label="분석이 끝났어요", state="complete")
        clear_after_analysis()
        ss.material, ss.material_bytes = material, (data if material["kind"] == "pdf" else None)
        ss.transcript, ss.transcript_source = transcript, source
        ss.concepts, ss.meta_pages, ss.utterances, ss.scores = cres["concepts"], meta, utts, scores
        ss.run_id, ss.from_sample = rid, from_sample
        ss.usage.merge(usage)
        ss.step = 2
        done = True
    except ExtractError as e:
        show_error(e.code, e)
    except NoConceptsError as e:
        show_error("E-09", e)
    except LLMError as e:
        ss.usage.merge(usage)
        show_error(error_code(e), e)
    except Exception as e:  # 잡히지 않은 예외
        show_error("UNKNOWN", e)
    finally:
        if not done:
            give_back_analysis()
    if done:
        st.rerun()


def page_s01() -> None:
    header("빈틈노트", "강의자료와 교수님 강의 녹음(또는 대본)을 올리면 출제 포인트, 내 빈틈, 공부 순서, 요약 노트를 만들어 줘요.")
    st.info(DISCLAIMER)
    st.caption(DATA_NOTICE)
    if is_fake():
        st.warning("가짜 AI 모드(BINTM_FAKE_AI=1)로 실행 중이에요. 결과는 저장된 예시 답이라 실제 AI 결과가 아니에요.")
    key_ok = has_key()
    if not key_ok:
        show_error("E-06")

    up = st.file_uploader("강의자료 (PDF 또는 PPTX, 최대 30MB)", type=["pdf", "pptx"], key="up_material")
    data, name = None, None
    if up is not None:
        data, name = up.getvalue(), up.name
        try:
            m = extract(data, name)
            st.caption(f"📄 {name} · {m['n_pages']}쪽")
        except ExtractError as e:
            show_error(e.code)
            data = None

    tab_audio, tab_paste = st.tabs(["🎙️ 녹음 파일", "📝 대본 붙여넣기"])
    with tab_audio:
        stt_ok = stt.available()
        audio = st.file_uploader("강의 녹음 (m4a, mp3, wav · 최대 25MB)", type=["m4a", "mp3", "wav"],
                                 key="up_audio", max_upload_size=config.MAX_AUDIO_MB, disabled=not stt_ok)
        st.caption("교수님 허락을 받은 녹음만, 개인 학습 목적으로만 올려 주세요.")
        if not stt_ok:
            st.caption("지금은 음성 인식을 쓸 수 없어요. 대본 붙여넣기를 써 주세요.")
    with tab_paste:
        paste = st.text_area("받아쓴 대본", key="paste_text", height=180,
                             placeholder="휴대폰 녹음 앱의 받아쓰기 기능 등으로 만든 대본을 붙여 넣어 주세요.")
    st.caption("녹음·대본이 없어도 분석할 수 있어요(녹음 신호만 빠져요).")

    c1, c2 = st.columns(2)
    start = c1.button("분석 시작", type="primary", width="stretch", disabled=not (key_ok and data))
    sample = c2.button("샘플로 체험", width="stretch", disabled=not key_ok,
                       help="가상 강의자료(자료구조 8장 트리와 힙, 20쪽)와 녹음 대본으로 바로 써 봐요.")
    left = session_left(ss.analyses_used, config.MAX_ANALYSES_PER_SESSION)
    if 0 <= left <= 2:
        st.caption(f"이 화면에서 분석은 {left}번 더 할 수 있어요.")
    st.caption("새로고침하면 결과가 사라져요. 결과는 ④에서 내려받기로 저장할 수 있어요.")
    if start and data:
        run_analysis(data, name, paste, audio if stt_ok else None, from_sample=False)
    if sample:
        run_analysis(SAMPLE_PDF.read_bytes(), SAMPLE_PDF.name, SAMPLE_TRANSCRIPT.read_text(encoding="utf-8"),
                     None, from_sample=True)


# ---- S02 ----
def page_s02() -> None:
    header("출제 포인트 레이더", "자료와 교수님 말에서 찾은 출제 신호로 개념 순위를 매겼어요.")
    scores = ss.scores
    n_utt = sum(1 for u in ss.utterances if u.get("concept_id"))
    targets = all_targets()
    c1, c2, c3 = st.columns(3)
    c1.metric("찾은 개념", len(scores))
    c2.metric("교수님 강조", n_utt)
    c3.metric("진단할 개념", len(current_targets()))
    st.info(DISCLAIMER)
    if not ss.transcript:
        st.caption("녹음 없이 자료만으로 계산했어요. 녹음을 넣으면 순위가 더 정확해져요.")
    elif not ss.utterances:
        st.warning(ERR["E-10"])
    rows, dim_started = [], False
    n_low = sum(1 for s in scores if s["pct"] < config.DIAG_MIN_PCT)
    for s in scores:
        low = s["pct"] < config.DIAG_MIN_PCT
        if low and not dim_started:
            dim_started = True
            rows.append(f'<div class="muted" style="margin-top:10px">아래 {n_low}개는 출제 가능성 점수가 '
                        f'{config.DIAG_MIN_PCT}점 미만이라 진단하지 않고 \'복습만\'으로 둬요</div>')
        rows.append(f'<div class="rankrow {"dim" if low else ""}"><b>{s["rank"]}. {export.esc(s["name"])}</b>'
                    f'<span style="float:right"><b>{s["pct"]}점</b></span>'
                    f'<div class="bar"><i style="width:{s["pct"]}%"></i></div>{export.reason_badges(s)}</div>')
    H("".join(rows))
    st.caption("출제 가능성 점수는 자료와 녹음의 신호를 정해진 규칙(가중치 v0)으로 더해, 가장 높은 개념을 100점으로 "
               "맞춘 비교용 점수예요. 확률이 아니며 실제 출제를 보장하지 않습니다. AI가 찾은 신호가 같으면 점수도 같아요.")
    by_id = concept_by_id()
    with st.expander("점수 내역과 교수님이 한 말 자세히 보기"):
        for s in scores:
            c = by_id.get(s["concept_id"], {})
            parts = [f"<h4 style='margin:12px 0 2px'>{s['rank']}. {export.esc(s['name'])} · {s['pct']}점</h4>",
                     f"<div>{export.esc(c.get('summary', ''))}</div>",
                     f"<div class='muted'>등장 페이지 {export.page_badges(c.get('pages', []))}</div><ul>"]
            for r in s["reasons"]:
                parts.append(f"<li>{export.esc(r['label'])} <b>{r['points']:+.2f}</b></li>")
            parts.append("</ul>")
            if c.get("objective_quote"):
                parts.append(f"<div class='muted'>학습목표: “{export.esc(c['objective_quote'])}”</div>")
            H("".join(parts))
        others = [u for u in ss.utterances if not u.get("concept_id")]
        if others:
            H("<h4>개념 목록 밖 언급</h4><ul>" + "".join(
                f"<li>{export.esc(u['concept_name'])}: “{export.esc(u['quote'])}”</li>" for u in others) + "</ul>")

    locked = bool(ss.grading)
    if "w_q_mode" not in st.session_state:
        st.session_state.w_q_mode = ss.q_mode
    st.radio("문제 형식", Q_MODES, key="w_q_mode", horizontal=True, disabled=locked,
             help=f"섞어서: 출제 점수 {config.ESSAY_MIN_PCT}점 이상은 서술형, 나머지는 객관식")
    ss.q_mode = st.session_state.w_q_mode
    if len(targets) > config.QUICK_DIAG_TOP:
        if "w_quick" not in st.session_state:
            st.session_state.w_quick = ss.quick_diag
        st.toggle(f"빠른 진단: 출제 가능성 상위 {config.QUICK_DIAG_TOP}개만 풀기", key="w_quick", disabled=locked,
                  help=f"{len(targets)}문제 대신 {config.QUICK_DIAG_TOP}문제만 풀어요. 나머지 "
                       f"{len(targets) - config.QUICK_DIAG_TOP}개는 '진단 안 함'(이해도 0.5)으로 공부 순서를 계산해요.")
        ss.quick_diag = st.session_state.w_quick
    else:
        ss.quick_diag = False
    n = len(current_targets())
    if n == 0:
        st.info("출제 가능성 점수 20점 이상인 개념이 없어 진단할 문제가 없어요.")
    st.button(f"{n}개 개념 진단하기", type="primary", disabled=n == 0, on_click=go, args=(3,))


# ---- S03 ----
def ensure_questions() -> None:
    by_id, pct = concept_by_id(), pct_by_id()
    ss.diag_ids = current_targets()
    need = []
    for cid in ss.diag_ids:
        if cid in ss.grading:
            continue
        kind = diagnose.choose_kind(pct[cid], ss.q_mode)
        q = ss.questions.get(cid)
        tag = f"{cid}|{kind}"
        if (q is None or q.get("requested_kind") != kind) and tag not in ss.q_attempted:
            need.append((cid, kind, tag))
    if not need:
        return
    targets = [{"concept": by_id[cid], "pct": pct[cid]} for cid, _, _ in need]
    # 형식은 요청한 대로 만들도록 개념별 q_mode를 맞춘다
    with st.spinner(f"진단 문제 {len(need)}개를 만드는 중이에요… (보통 20~40초)"):
        groups = {}
        for t, (cid, kind, tag) in zip(targets, need):
            groups.setdefault(kind, []).append(t)
        all_names = [by_id[c]["name"] for c in ss.diag_ids]
        for kind, ts in groups.items():
            mode = "모두 서술형" if kind == ESSAY else "모두 객관식"
            qs, failed, u, err = make_questions_with_names(ts, mode, all_names)
            ss.usage.merge(u)
            for cid, q in qs.items():
                q["requested_kind"] = kind
                ss.questions[cid] = q
            ss.q_failed = sorted(set(ss.q_failed) | set(failed))
            if err:
                ss.q_error = f"{type(err).__name__}: {err}"
    ss.q_attempted = ss.q_attempted + [tag for _, _, tag in need]


def make_questions_with_names(targets, mode, all_names):
    """다른 개념 목록은 함께 진단하는 전체 개념 이름으로 만든다."""
    cache = sample_cache() if ss.from_sample else None
    # make_questions는 targets 안의 이름으로 다른 개념 목록을 만들므로, 전체 이름을 넣기 위해 가짜 대상 없이 직접 부른다
    from core.diagnose import make_questions
    return make_questions(targets, ss.material, ss.meta_pages, mode, cache=cache, run_id=ss.run_id,
                          all_names=all_names)


def fill_examples() -> None:
    """예시 답 채우기 (F11). 입력칸이 그려지기 전에 세션 키에 넣는다."""
    qs = {cid: ss.questions[cid] for cid in shown_questions() if cid not in ss.grading}
    for cid, v in diagnose.example_answers(qs).items():
        if "answer" in v:
            st.session_state[f"ans_{cid}"] = v["answer"]
            st.session_state[f"dk_{cid}"] = v["dont_know"]
            ss.answers[cid], ss.dont_know[cid] = v["answer"], v["dont_know"]
        else:
            st.session_state[f"mcq_{cid}"] = v["choice"]
            st.session_state[f"guess_{cid}"] = v["guessed"]
            st.session_state[f"conf_{cid}"] = v["confusion"]
            ss.mcq_choice[cid], ss.guessed[cid], ss.confusion[cid] = v["choice"], v["guessed"], v["confusion"]
    ss.show_missing = False


def restore(key: str, value) -> None:
    """화면에 그리지 않아 지워진 입력칸 값을 세션 딕셔너리에서 되살린다."""
    if key not in st.session_state and value is not None:
        st.session_state[key] = value


def answered(cid: str) -> bool:
    q = ss.questions[cid]
    return diagnose.is_answered(q, ss.answers.get(cid), ss.dont_know.get(cid), ss.mcq_choice.get(cid))


def draw_question(i: int, cid: str) -> None:
    q = ss.questions[cid]
    pct = pct_by_id()[cid]
    g = ss.grading.get(cid)
    locked = g is not None
    with st.container(border=True):
        H(f'<div><b>Q{i}. {export.esc(q["concept_name"])}</b> <span class="badge">{q["kind"]}</span>'
          f'<span class="badge">출제 점수 {pct}</span></div><div class="q" style="margin-top:6px">'
          f'{export.esc(q["question"])}</div>{export.figure_html(q.get("figure"))}')
        if q["kind"] == ESSAY:
            restore(f"ans_{cid}", ss.answers.get(cid))
            restore(f"dk_{cid}", ss.dont_know.get(cid))
            st.text_area("내 답", key=f"ans_{cid}", placeholder="아는 만큼 2~3문장으로 적어 주세요.",
                         disabled=locked, height=110)
            st.checkbox("모르겠어요", key=f"dk_{cid}", disabled=locked)
            ss.answers[cid] = st.session_state.get(f"ans_{cid}", "") or ""
            ss.dont_know[cid] = bool(st.session_state.get(f"dk_{cid}"))
        else:
            restore(f"mcq_{cid}", ss.mcq_choice.get(cid))
            opts = [0, 1, 2, 3, -1]
            labels = {k: f"{CHOICE_MARKS[k]} {q['choices'][k]}" for k in range(4)}
            labels[-1] = "모르겠어요"
            kwargs = {} if f"mcq_{cid}" in st.session_state else {"index": None}
            st.radio("보기를 골라 주세요", opts, key=f"mcq_{cid}", format_func=lambda k: labels[k],
                     disabled=locked, **kwargs)
            choice = st.session_state.get(f"mcq_{cid}")
            ss.mcq_choice[cid] = choice
            if choice is not None and choice != -1:
                restore(f"guess_{cid}", ss.guessed.get(cid))
                st.checkbox("확신 없이 골랐어요 (찍었어요)", key=f"guess_{cid}", disabled=locked)
                ss.guessed[cid] = bool(st.session_state.get(f"guess_{cid}"))
                if ss.guessed[cid]:
                    restore(f"conf_{cid}", ss.confusion.get(cid))
                    st.text_area("어떤 점이 헷갈렸나요? (선택)", key=f"conf_{cid}", max_chars=config.CONFUSION_MAX_CHARS,
                                 placeholder="②와 ③ 중에 고민했어요. 두 방법이 어떻게 다른지 모르겠어요.",
                                 disabled=locked, height=80)
                    ss.confusion[cid] = st.session_state.get(f"conf_{cid}", "") or ""
                else:
                    ss.confusion[cid] = ""
            else:
                ss.guessed[cid], ss.confusion[cid] = False, ""
        if ss.show_missing and not locked and not answered(cid):
            H(f'<div class="red">{ERR["E-11"]}</div>')
        if cid in ss.grade_failed:
            H('<div class="red">이 문제는 채점하지 못했어요. 답은 그대로 있어요. 아래 \'채점 못한 문제 다시 채점\'을 눌러 주세요.</div>')
        if g:
            draw_result(cid, q, g)


def draw_result(cid: str, q: dict, g: dict) -> None:
    et = f" · {export.esc(g['error_type'])}" if g.get("error_type") else ""
    H(f'<div style="margin-top:8px">{status_badge(g["status"])} <b>{g["score"]}/10</b>{et}</div>'
      f'<div>{export.with_pages(g.get("reason", ""))}</div>')
    if q["kind"] == MCQ:
        mine = ss.mcq_choice.get(cid)
        items = []
        for k, ch in enumerate(q["choices"]):
            cls = "ok" if k == q["answer_index"] else ("bad" if k == mine else "")
            tag = " · 정답" if k == q["answer_index"] else ""
            tag += " · 내 답" if k == mine else ""
            items.append(f'<li class="{cls}">{CHOICE_MARKS[k]} {export.esc(ch)}<b>{tag}</b></li>')
        conf = ss.confusion.get(cid) if ss.guessed.get(cid) else ""
        H(f'<ol class="choices">{"".join(items)}</ol>'
          + (f'<div class="conf"><b>💬 내가 헷갈린 점</b><br>{export.esc(conf)}</div>' if conf else "")
          + f'<div class="muted">해설</div>{export.paras(q.get("explanation", ""))}'
          + f'<div class="muted">근거 {export.page_badges(q.get("source_pages"))}</div>')
    else:
        with st.expander("모범 답안과 채점 기준 보기"):
            rub = "".join(f"<li>{export.esc(r['point'])} ({sc}/{r['score']})</li>"
                          for r, sc in zip(q.get("rubric", []), g.get("rubric_scores") or [0] * 10))
            H(f'{export.paras(q.get("answer", ""))}<ul>{rub}</ul>'
              f'<div class="muted">근거 {export.page_badges(q.get("source_pages"))}</div>')


def do_grade() -> None:
    qs = [cid for cid in shown_questions() if cid not in ss.grading]
    missing = [i for i, cid in enumerate(shown_questions(), start=1) if cid in qs and not answered(cid)]
    if missing:
        ss.show_missing = True
        ss.missing_list = missing
        return
    ss.show_missing, ss.missing_list = False, []
    only = list(ss.grade_failed) if ss.grade_failed else qs
    with st.spinner("채점하는 중이에요… (서술형은 AI가 채점해요)"):
        grading, failed, u, err = diagnose.grade_all(
            {cid: ss.questions[cid] for cid in shown_questions()}, ss.answers, ss.dont_know, ss.mcq_choice,
            ss.guessed, ss.material, ss.meta_pages, concept_by_id(), only=only)
    ss.usage.merge(u)
    ss.grading.update(grading)
    ss.grade_failed = failed
    ss.grade_error = f"{type(err).__name__}: {err}" if err else None
    ss.priorities, ss.s04_attempted = None, []


def page_s03() -> None:
    header("내 취약점 진단", f"출제 가능성 점수 {config.DIAG_MIN_PCT}점 이상인 개념을 한 문제씩 확인해요. "
                         "찍어서 맞힌 것은 '헷갈림'으로 봐요.")
    try:
        ensure_questions()
    except NoKeyError as e:
        show_error("E-06", e)
    qids = shown_questions()
    if ss.q_failed:
        st.warning(f"문제를 만들지 못한 개념 {len(ss.q_failed)}개는 진단에서 뺐어요: " + ", ".join(ss.q_failed))
        if ss.q_error:
            with st.expander("자세한 오류"):
                st.code(ss.q_error)
        if st.button("못 만든 문제 다시 만들기"):
            ss.q_attempted, ss.q_failed, ss.q_error = [], [], None
            st.rerun()
    if not qids:
        if ss.q_failed:
            show_error("E-08")
        return
    if ss.grade_failed:
        st.error(f"서술형 {len(ss.grade_failed)}문제를 채점하지 못했어요. 답은 그대로 있어요. "
                 "'채점 못한 문제 다시 채점'을 눌러 주세요.")
        if ss.grade_error:
            with st.expander("자세한 오류"):
                st.code(ss.grade_error)
    if all(c in ss.grading for c in qids):
        cnt = {s: sum(1 for c in qids if ss.grading[c]["status"] == s) for s in ("앎", "헷갈림", "모름")}
        c1, c2, c3 = st.columns(3)
        c1.metric("앎", cnt["앎"])
        c2.metric("헷갈림", cnt["헷갈림"])
        c3.metric("모름", cnt["모름"])
    n_ans = sum(1 for c in qids if c in ss.grading or answered(c))
    n_mcq = sum(1 for c in qids if ss.questions[c]["kind"] == MCQ)
    st.progress(n_ans / len(qids), text=f"답한 문제 {n_ans} / {len(qids)} · 객관식 {n_mcq} · 서술형 {len(qids) - n_mcq}")
    if ss.from_sample and n_ans < len(qids) and not ss.grading:
        st.caption("샘플로 둘러보는 중이라면 '예시 답 채우기'로 바로 채점까지 가 볼 수 있어요.")
        st.button("예시 답 채우기 (샘플 체험용)", on_click=fill_examples)
    for i, cid in enumerate(qids, start=1):
        draw_question(i, cid)
    pending = [c for c in qids if c not in ss.grading]
    if pending:
        st.caption("모든 문제에 답해야 채점해요. 모르면 '모르겠어요'를 고르면 돼요.")
        label = "채점 못한 문제 다시 채점" if ss.grade_failed else "채점하기"
        if st.button(label, type="primary", width="stretch"):
            do_grade()
            st.rerun()
        if ss.show_missing and ss.missing_list:
            H(f'<div class="red">아직 답하지 않은 문제: {", ".join(f"Q{i}" for i in ss.missing_list)}</div>')
        if ss.grade_failed and st.button("채점 못한 문제는 빼고 공부 순서 보기"):
            ss.grade_skip = True
            ss.step = 4
            st.rerun()
    else:
        st.button("공부 순서 보기", type="primary", width="stretch", on_click=go, args=(4,))


# ---- S04 ----
def explain_job(cid: str) -> dict:
    pr = {p["concept_id"]: p for p in ss.priorities}[cid]
    q = ss.questions.get(cid) if cid in ss.grading else None
    return {"concept": concept_by_id()[cid], "pct": pr["exam_pct"], "status": pr["status"], "q": q,
            "g": ss.grading.get(cid), "answer": ss.answers.get(cid, ""), "choice": ss.mcq_choice.get(cid),
            "guessed": ss.guessed.get(cid), "confusion": ss.confusion.get(cid, "") if ss.guessed.get(cid) else ""}


def note_job(p: dict, detail: str) -> dict:
    return {"concept": concept_by_id()[p["concept_id"]], "detail": detail, "pr": p,
            "g": ss.grading.get(p["concept_id"]), "utterances": ss.utterances}


def run_s04_jobs(exp_ids: list[str], note_ids: list[str], label: str) -> None:
    pr = {p["concept_id"]: p for p in ss.priorities}
    jobs = {("exp", cid): explain_job(cid) for cid in exp_ids}
    for cid in note_ids:
        p = pr[cid]
        jobs[("note", cid)] = note_job(p, note.detail_level(p["action"], p["exam_pct"], p["status"]))
    if not jobs:
        return
    material, meta = ss.material, ss.meta_pages

    def do(job, u):
        if "detail" in job:
            return note.make_note(job, material, meta, u)
        return explain.explain(job, material, meta, u)

    with st.spinner(label):
        res, failed, u, err = explain.run_parallel(do, jobs)
    ss.usage.merge(u)
    for (kind, cid), v in res.items():
        if kind == "exp":
            ss.explanations[cid] = v
            ss.explain_failed = [c for c in ss.explain_failed if c != cid]
        else:
            ss.notes[cid] = v
            ss.notes_failed = [c for c in ss.notes_failed if c != cid]
    for kind, cid in failed:
        if kind == "exp" and cid not in ss.explain_failed:
            ss.explain_failed = ss.explain_failed + [cid]
        if kind == "note" and cid not in ss.notes_failed:
            ss.notes_failed = ss.notes_failed + [cid]
    if err:
        ss.errors = ss.errors + [f"{type(err).__name__}: {err}"]


def ensure_s04() -> None:
    if ss.priorities is None:
        ss.priorities = priority.compute_priorities(ss.scores, ss.grading)
    by_id = concept_by_id()
    conf = {cid: t for cid, t in ss.confusion.items() if ss.guessed.get(cid) and cid in ss.grading}
    exp_ids = [cid for cid in explain.auto_targets(ss.priorities, conf)
               if cid not in ss.explanations and f"exp|{cid}" not in ss.s04_attempted]
    note_ids = []
    for p in ss.priorities:
        cid = p["concept_id"]
        d = note.detail_level(p["action"], p["exam_pct"], p["status"])
        if d == "짧게":
            if cid not in ss.notes:
                ss.notes[cid] = note.short_note(by_id[cid], ss.meta_pages)
        elif cid not in ss.notes and f"note|{cid}" not in ss.s04_attempted:
            note_ids.append(cid)
    if exp_ids or note_ids:
        ss.s04_attempted = ss.s04_attempted + [f"exp|{c}" for c in exp_ids] + [f"note|{c}" for c in note_ids]
        run_s04_jobs(exp_ids, note_ids, f"보완 설명 {len(exp_ids)}개와 요약 노트 {len(note_ids)}개를 만드는 중이에요… "
                                        "(보통 30~60초)")


def export_state() -> dict:
    keys = ["material", "transcript_source", "scores", "priorities", "questions", "grading", "answers", "dont_know",
            "mcq_choice", "guessed", "confusion", "explanations", "notes", "concepts", "meta_pages", "utterances"]
    st_ = {k: ss[k] for k in keys}
    st_["confusion"] = {c: t for c, t in ss.confusion.items() if ss.guessed.get(c)}
    st_["questions"] = {c: q for c, q in ss.questions.items() if c in ss.grading}
    st_["date"] = dt.date.today().isoformat()
    return st_


def download_buttons(where: str) -> None:
    state = export_state()
    today = dt.date.today().strftime("%Y%m%d")
    c1, c2 = st.columns(2)
    c1.download_button("📥 공부 순서·오답노트 내려받기", export.study_html(state).encode("utf-8"),
                       file_name=f"빈틈노트_공부순서_오답노트_{today}.html", mime="text/html",
                       key=f"dl_study_{where}", width="stretch")
    c2.download_button("📒 요약 노트 내려받기", export.notes_html(state).encode("utf-8"),
                       file_name=f"빈틈노트_요약노트_{today}.html", mime="text/html",
                       key=f"dl_notes_{where}", width="stretch")


def page_images(pages: list[int], key: str) -> None:
    if not ss.material_bytes or not pages:
        return
    pages = pages[:2]
    with st.expander("강의자료 원본 보기 · " + ", ".join(f"p.{p}" for p in pages)):
        for p in pages:
            img = cached_page_jpeg(ss.run_id, p, ss.material_bytes)
            if img:
                st.image(img, caption=f"p.{p}", width="stretch")


def study_card(p: dict) -> None:
    cid = p["concept_id"]
    state = export_state()
    q = state["questions"].get(cid)
    g = ss.grading.get(cid)
    ex = ss.explanations.get(cid)
    with st.container(border=True):
        H(f'<h3 style="margin:0">{p["rank"]}. {export.esc(p["name"])}</h3><div>{status_badge(p["status"])}'
          f'<span class="badge">출제 점수 {p["exam_pct"]}</span><span class="badge">우선순위 {p["priority"]}</span></div>')
        if q and g:
            with st.expander(f"📝 내 문제와 답 다시 보기 · {g['status']} {g['score']}/10"):
                H(export.question_block(q, state, cid) + export.grading_block(q, g))
        conf = state["confusion"].get(cid, "")
        if ex:
            H(export.explanation_block(ex, conf, (q or {}).get("source_pages") or []))
            page_images(ex.get("check_pages") or ex.get("source_pages") or [], f"ex_{cid}")
        elif cid in ss.explain_failed:
            H('<div class="red">설명을 만들지 못했어요.</div>')
            if st.button("설명 다시 만들기", key=f"reexp_{cid}"):
                run_s04_jobs([cid], [], "설명을 다시 만드는 중이에요…")
                st.rerun()
        else:
            if st.button("설명 보기", key=f"exp_{cid}"):
                run_s04_jobs([cid], [], "설명을 만드는 중이에요…")
                st.rerun()


def page_s04() -> None:
    header("우선순위 보완 학습", "출제 점수 × 모르는 정도로 공부 순서를 정했어요. 위에서부터 보면 돼요.")
    ensure_s04()
    pri = ss.priorities
    counts = {a: [p for p in pri if p["action"] == a] for a in ("지금 당장", "다음", "복습만")}
    c1, c2, c3 = st.columns(3)
    c1.metric("지금 당장", len(counts["지금 당장"]))
    c2.metric("다음", len(counts["다음"]))
    c3.metric("복습만", len(counts["복습만"]))
    download_buttons("top")
    if ss.errors:
        with st.expander("자세한 오류"):
            st.code("\n".join(ss.errors[-5:]))
    tab1, tab2 = st.tabs(["🎯 공부 순서와 오답노트", "📒 시험 대비 요약 노트"])
    with tab1:
        st.subheader(f"지금 당장 · {len(counts['지금 당장'])}개")
        st.caption(export.ACTION_DESC["지금 당장"])
        for p in counts["지금 당장"]:
            study_card(p)
        st.subheader(f"다음 · {len(counts['다음'])}개")
        st.caption(export.ACTION_DESC["다음"])
        todo = [p["concept_id"] for p in counts["다음"] if p["concept_id"] not in ss.explanations]
        if todo and st.button(f"'다음' 개념 설명 {len(todo)}개 한 번에 보기"):
            run_s04_jobs(todo, [], f"설명 {len(todo)}개를 만드는 중이에요…")
            st.rerun()
        for p in counts["다음"]:
            study_card(p)
        with st.expander(f"복습만 · {len(counts['복습만'])}개"):
            st.caption(export.ACTION_DESC["복습만"] + " '진단 안 함'은 출제 가능성 점수가 20점 미만이라 문제를 내지 않은 개념이에요.")
            for p in counts["복습만"]:
                study_card(p)
        with st.expander("전체 표로 보기"):
            rows = "".join(
                f'<tr><td>{p["rank"]}</td><td>{export.esc(p["name"])}</td>'
                f'<td><div class="bar"><i style="width:{p["exam_pct"]}%"></i></div>{p["exam_pct"]}점</td>'
                f'<td>{status_badge(p["status"])}</td>'
                f'<td><div class="bar"><i style="width:{p["priority"]}%"></i></div>{p["priority"]}</td>'
                f'<td>{p["action"]}</td></tr>' for p in pri)
            H('<div style="overflow-x:auto"><table class="tbl"><tr><th>순위</th><th>개념</th><th>출제 점수</th>'
              f'<th>이해 상태</th><th>우선순위</th><th>권장</th></tr>{rows}</table></div>')
            st.caption("우선순위 = 출제 점수 × (1 − 이해도). 이해도: 앎 1.0 · 헷갈림 0.5 · 모름 0.0 · 진단 안 함 0.5. "
                       "50 이상 지금 당장, 20~49 다음, 20 미만 복습만.")
    with tab2:
        notes = ss.notes
        cnt = {d: sum(1 for n in notes.values() if n["detail"] == d) for d in note.DETAILS}
        st.caption(f"강의 순서대로 모든 개념을 정리했어요. 자세히 {cnt['자세히']} · 보통 {cnt['보통']} · 짧게 {cnt['짧게']}")
        pr = {p["concept_id"]: p for p in pri}
        by_id = concept_by_id()
        for i, cid in enumerate(note.lecture_order(ss.concepts, ss.meta_pages), start=1):
            with st.container(border=True):
                if cid in notes:
                    H(export.note_card(i, notes[cid], by_id[cid], pr.get(cid), ss.utterances))
                    page_images(notes[cid].get("source_pages") or [], f"note_{cid}")
                else:
                    H(f'<h3 style="margin:0">{i}. {export.esc(by_id[cid]["name"])}</h3>'
                      '<div class="red">요약 노트를 만들지 못했어요.</div>')
                    if st.button("요약 노트 다시 만들기", key=f"renote_{cid}"):
                        run_s04_jobs([], [cid], "요약 노트를 다시 만드는 중이에요…")
                        st.rerun()
    download_buttons("bottom")
    st.button("다른 자료로 다시", on_click=reset_all)


# ---- S05 ----
def page_s05() -> None:
    header("안내·설정", "빈틈노트 사용 방법과 현재 설정이에요.")
    st.markdown("**사용 방법**\n\n1. 강의자료(PDF/PPTX)와 녹음 또는 대본을 올려요.\n2. ②에서 출제 포인트 순위를 봐요.\n"
                "3. ③에서 진단 문제를 풀어요(모르면 '모르겠어요').\n4. ④에서 공부 순서·오답노트와 요약 노트를 보고 내려받아요.")
    st.markdown("**주의**")
    st.markdown(f"- {DISCLAIMER}\n- 녹음은 교수님 허락을 받은 것만, 개인 학습 목적으로만 올려 주세요.\n- {DATA_NOTICE}")
    u = ss.usage
    st.markdown("**현재 설정**")
    items = [("언어 모델", config.LLM_MODEL + (" (가짜 AI 모드)" if is_fake() else "")),
             ("음성 인식", "사용 가능" if stt.available() else "사용 안 함(대본 붙여넣기)"),
             ("진단 기준", f"출제 가능성 점수 {config.DIAG_MIN_PCT}점 이상 전부"), ("문제 형식", ss.q_mode),
             ("가중치 버전", score.WEIGHTS_VERSION), ("이번 세션 AI 호출 수", f"{u.calls}번"),
             ("입력 토큰", f"{u.input_tokens:,}"), ("출력 토큰", f"{u.output_tokens:,}"),
             ("이 화면 남은 분석 횟수", str(session_left(ss.analyses_used, config.MAX_ANALYSES_PER_SESSION)))]
    H('<table class="tbl">' + "".join(f"<tr><th>{k}</th><td>{export.esc(v)}</td></tr>" for k, v in items) + "</table>")
    st.caption("AI 호출 수는 호출마다 세요. 저장된 결과를 다시 쓰면 AI를 부르지 않았으므로 더하지 않아요.")
    st.markdown(f"**정보**\n\n- 팀: {config.TEAM_NAME}\n- 대회: {config.EVENT_NAME}\n- 저장소: {config.REPO_URL}")


def main() -> None:
    global ss
    st.set_page_config(page_title="빈틈노트", page_icon="📝", layout="centered")
    st.markdown(CSS, unsafe_allow_html=True)
    load_secrets()
    init_state()
    ss = st.session_state
    if ss.step in (2, 3, 4) and not can_open(ss.step):
        ss.step = 1
    sidebar()
    {1: page_s01, 2: page_s02, 3: page_s03, 4: page_s04, 5: page_s05}[ss.step]()


main()
