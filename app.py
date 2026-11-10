"""빈틈노트 화면 (S01~S05)과 사이드바. 계산은 core/에 있고 이 파일은 부르기만 한다."""
from __future__ import annotations

import html
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# --- 배포 뒤 예전 모듈 버리기 (12장) : core·config를 import하기 전에 ---
def _watched_files() -> dict:
    files = [ROOT / "config.py"] + sorted((ROOT / "core").glob("*.py")) + sorted((ROOT / "prompts").glob("*.md"))
    return {str(p): p.stat().st_mtime for p in files if p.exists()}


def _is_stale(old: dict | None, now: dict) -> bool:
    """파일 시각이 바뀌었으면 True. 프롬프트(.md)는 지난 기록에 없어도 바뀐 것으로 본다."""
    old = old or {}
    for path, t in now.items():
        if path.endswith(".md"):
            if old.get(path) != t:
                return True
        elif path in old and old[path] != t:
            return True
    return False


def _drop_stale_modules() -> None:
    now = _watched_files()
    if _is_stale(getattr(sys, "_bintm_mtimes", None), now):
        for name in list(sys.modules):
            if name in ("config", "core") or name.startswith("core."):
                del sys.modules[name]
        st.cache_resource.clear()
    sys._bintm_mtimes = now


_drop_stale_modules()

import config  # noqa: E402
from core import concepts as CC  # noqa: E402
from core import diagnose as DG  # noqa: E402
from core import explain as EX  # noqa: E402
from core import export as EP  # noqa: E402
from core import extract as XT  # noqa: E402
from core import guard as GD  # noqa: E402
from core import note as NT  # noqa: E402
from core import pageimg as PI  # noqa: E402
from core import priority as PR  # noqa: E402
from core import score as SC  # noqa: E402
from core import stt as STT  # noqa: E402
from core import utterances as UT  # noqa: E402
from core.figure import figure_html  # noqa: E402
from core.llm import KeyMissingError, LLMError, Usage, error_info, fake_mode, has_llm_key, set_keys  # noqa: E402

st.set_page_config(page_title="빈틈노트", page_icon="📝", layout="centered")

DISCLAIMER = "출제를 보장하지 않습니다. 공부 우선순위를 정하는 참고용입니다."
SCORE_NOTE = ("출제 가능성 점수는 자료와 녹음의 신호를 정해진 규칙(가중치 v0)으로 더해, 가장 높은 개념을 100점으로 맞춘 "
              "비교용 점수예요. 확률이 아니며 실제 출제를 보장하지 않습니다.")
DATA_NOTICE = ("올린 자료와 녹음은 분석을 위해 AI 제공사(Anthropic, OpenAI) 서버로 전송됩니다. 올린 파일은 서버 디스크에 "
               "저장하지 않고, 결과는 이 브라우저 화면(세션)에 둡니다. 같은 파일을 다시 분석할 때를 위해 개념·강조 분석 결과와 "
               "쪽 그림은 서버 메모리 캐시에 잠시 남고, 서버가 다시 켜지면 사라집니다. 학번·전화번호·이메일은 AI에 보내기 전에 가립니다.")
E05 = "녹음을 글자로 바꾸지 못해 녹음 없이 계산했어요. 대본 붙여넣기로 다시 분석할 수 있어요"
E11_CARD = "아직 답하지 않았어요. 모르면 '모르겠어요'를 골라 주세요."
E14 = "새로고침하면 결과가 사라져요. 결과는 ④에서 내려받기로 저장할 수 있어요"
E16 = (f"이 화면에서는 분석을 {config.MAX_ANALYSES_PER_SESSION}번까지 할 수 있어요. "
       "지금 결과는 ②~④에서 계속 볼 수 있어요.")
E17 = ("오늘 이 앱에서 쓸 수 있는 분석 횟수를 다 썼어요. 내일 다시 이용해 주세요. "
       "직접 실행하려면 README의 로컬 실행 방법을 보세요.")
UNKNOWN = "알 수 없는 오류가 났어요. 처음부터 다시 해 주세요"
SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"
REPO_URL = "https://github.com/dodohun2212/bintm-rehearsal"
MARKS = ("①", "②", "③", "④")
STEP_NAMES = ["① 자료 올리기", "② 출제 포인트", "③ 취약점 진단", "④ 공부 순서", "⑤ 안내·설정"]

CSS = """
<style>
.block-container{max-width:860px;padding-top:4.5rem;padding-bottom:6rem}
.block-container p,.block-container li{font-size:17px;line-height:1.75}
[data-testid="stSpinner"]{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:9999;
 background:#ffffff;color:#1d2433;border:1px solid #c9d3e6;border-radius:999px;padding:8px 20px;
 box-shadow:0 6px 20px rgba(0,0,0,.15);max-width:92vw}
.stepper{display:flex;flex-wrap:wrap;gap:4px;align-items:center;font-size:14px;margin-bottom:6px}
.stepper span{padding:2px 10px;border-radius:999px;background:#eef1f6;color:#5f6b7a}
.stepper span.on{background:#2f5bd3;color:#fff;font-weight:600}.stepper span.done{background:#dfe8ff;color:#2f5bd3}
.stepper i{color:#9aa4b2;font-style:normal}
.sub{color:#5f6b7a;margin-top:-6px}
.badge{display:inline-block;font-size:13px;border:1px solid #d9dee7;border-radius:999px;padding:0 9px;margin:2px 3px 2px 0;white-space:nowrap}
.badge.neg{text-decoration:line-through;color:#8a94a3}.badge.kind{background:#eef1f6}
.st-앎{background:#e6f5ec;color:#1f8a4c;border-color:#bfe5cd}.st-헷갈림{background:#fff4dc;color:#a86b00;border-color:#f3dca6}
.st-모름{background:#fdeaea;color:#c43d3d;border-color:#f3c4c4}.st-진단{background:#eef1f6;color:#5f6b7a}
.pg{display:inline-block;font-size:13px;background:#eaf1ff;color:#2f5bd3;border-radius:6px;padding:0 6px;margin:0 2px}
.rank{display:flex;gap:10px;align-items:center;border:1px solid #e3e7ee;border-radius:10px;padding:8px 12px;margin:6px 0;flex-wrap:wrap}
.rank .no{font-weight:700;color:#2f5bd3;min-width:1.6em}.rank .nm{font-weight:600;flex:1 1 180px}
.rank .bar{flex:0 0 120px;height:8px;background:#e3e7ee;border-radius:6px}.rank .bar i{display:block;height:8px;border-radius:6px;background:#2f5bd3}
.rank .pt{font-weight:700;min-width:3.2em;text-align:right}.rank .bd{flex-basis:100%}
.rank.dim{opacity:.5}.cut{color:#5f6b7a;font-size:15px;margin:10px 0 2px}
.qtext{font-size:18px;font-weight:600;line-height:1.7;margin:4px 0 6px}
.missing,.failtxt{color:#c43d3d;font-weight:600}
.choice{margin:2px 0}.correct{color:#1f8a4c;font-weight:600}.mine{color:#c43d3d;font-weight:600}
.gap{border-left:4px solid #c43d3d;background:#fdeaea;padding:8px 12px;border-radius:6px;margin:8px 0;color:#1d2433}
.conf{border-left:4px solid #2f5bd3;background:#eaf1ff;padding:8px 12px;border-radius:6px;margin:8px 0;color:#1d2433}
.nf{border-left:4px solid #a86b00;background:#fff4dc;padding:8px 12px;border-radius:6px;margin:8px 0;color:#1d2433}
.info{color:#5f6b7a;font-size:15px}.figure{margin:6px 0 10px}.fig-cap{font-size:14px;color:#5f6b7a}
.figure table,.tbl{border-collapse:collapse}.figure td,.figure th,.tbl td,.tbl th{border:1px solid #d9dee7;padding:3px 9px;text-align:center}
.fig-array .idx th{color:#5f6b7a;font-weight:400}.tbl{width:100%;font-size:15px}
.tbl .mini{display:inline-block;width:60px;height:7px;background:#e3e7ee;border-radius:5px;vertical-align:middle;margin-right:4px}
.tbl .mini i{display:block;height:7px;background:#2f5bd3;border-radius:5px}
@media (max-width:640px){.rank .bar{flex-basis:80px}.qtext{font-size:17px}.block-container{padding-left:1rem;padding-right:1rem}}
</style>
"""


# --- 상태 ---
def _defaults() -> dict:
    return dict(step=1, material=None, material_bytes=None, run_id=None, from_sample=False,
                transcript=None, transcript_source=None, concepts=None, utterances=[], scores=None,
                meta_pages=[], q_mode="섞어서", quick_diag=False, diag_ids=[], questions={}, q_store={},
                q_fail={}, answers={}, dont_know={}, mcq_choice={}, guessed={}, confusion={},
                show_missing=False, grading={}, grade_failed=[], grade_error=None, q_failed=[],
                priorities=None, explanations={}, explain_failed=[], notes={}, notes_failed=[],
                model_name=config.LLM_MODEL, usage=Usage(), errors=[], notices=[], timings={},
                auto_done=False, item_errors={})


def init_state() -> None:
    ss = st.session_state
    for k, v in _defaults().items():
        if k not in ss:
            ss[k] = v
    if "analyses_used" not in ss:
        ss["analyses_used"] = 0


def reset_all() -> None:
    """'다른 자료로 다시': 분석 횟수(analyses_used)만 남기고 전부 지운다."""
    used = st.session_state.get("analyses_used", 0)
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.session_state["analyses_used"] = used
    init_state()


def _load_keys() -> None:
    """st.secrets → 환경변수 순. 키 값은 화면·로그에 쓰지 않는다."""
    vals = {}
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        try:
            v = st.secrets.get(name)
        except Exception:
            v = None
        if v:
            vals[name] = v
    set_keys(vals)


@st.cache_resource
def daily_counter() -> GD.DailyCounter:
    return GD.DailyCounter(config.MAX_ANALYSES_PER_DAY)


@st.cache_resource
def sample_cache() -> GD.ResultCache:
    return GD.ResultCache(max_items=200)


def take_analysis() -> str | None:
    """분석 1번을 센다. 막히면 에러 문구."""
    ss = st.session_state
    if GD.session_left(ss.analyses_used, config.MAX_ANALYSES_PER_SESSION) == 0:
        return "E-16"
    if not daily_counter().try_take():
        return "E-17"
    ss.analyses_used += 1
    return None


def give_back_analysis() -> None:
    ss = st.session_state
    ss.analyses_used = max(0, ss.analyses_used - 1)
    daily_counter().give_back()


# --- 캐시된 AI 호출 1·2 (같은 파일이면 다시 쓰고, 사용량을 더하지 않는다) ---
@st.cache_data(show_spinner=False, max_entries=64)
def cached_concepts(run_id: str, fake: bool, _material: dict, _ran: dict) -> dict:
    u = Usage()
    result = CC.extract_concepts(_material, u)
    _ran["usage"] = u
    return result


@st.cache_data(show_spinner=False, max_entries=64)
def cached_utterances(run_id: str, transcript: str, concepts_json: str, fake: bool,
                      _concepts: list, _ran: dict) -> list:
    u = Usage()
    result = UT.find_utterances(transcript, _concepts, u)
    _ran["usage"] = u
    return result


@st.cache_data(show_spinner=False, max_entries=256)
def cached_page_img(run_id: str, page_no: int, _data: bytes):
    return PI.page_jpeg(_data, page_no)


def run_parallel(items: list, fn, workers: int) -> list:
    """스레드 안에서는 세션을 읽거나 쓰지 않는다. 필요한 값은 items에 담아 넘긴다."""
    def work(item):
        u = Usage()
        try:
            return True, fn(item, u), u
        except Exception as exc:  # 한 개념이 실패해도 나머지는 살린다
            return False, exc, u
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(work, items))


# --- 작은 화면 조각 ---
def esc(t) -> str:
    return html.escape("" if t is None else str(t))


def md_safe(t: str) -> str:
    """라디오 보기처럼 마크다운으로 그려지는 곳에서 ~, $ 등이 바뀌지 않게."""
    out = str(t)
    for ch in "\\`*_~$#[]<>|":
        out = out.replace(ch, "\\" + ch)
    return out


def badge(text: str, cls: str = "") -> str:
    return f'<span class="badge {cls}">{esc(text)}</span>'


def status_badge(status: str) -> str:
    return badge(status, "st-진단" if status == "진단 안 함" else f"st-{status}")


def show_error(code: str | None, msg: str, detail: str | None = None) -> None:
    st.error(f"{msg} ({code})" if code else msg)
    if detail:
        with st.expander("자세한 오류"):
            st.code(detail)


def stepper(step: int) -> None:
    parts = []
    for i, name in enumerate(STEP_NAMES[:4], 1):
        cls = "on" if i == step else ("done" if i < step else "")
        parts.append(f'<span class="{cls}">{name}</span>')
    st.html('<div class="stepper">' + "<i>›</i>".join(parts) + "</div>")


def concept_map() -> dict:
    return {c["id"]: c for c in st.session_state.concepts or []}


def score_map() -> dict:
    return {s["concept_id"]: s for s in st.session_state.scores or []}


def step_open(n: int) -> bool:
    ss = st.session_state
    if n in (1, 5):
        return True
    if n in (2, 3):
        return ss.scores is not None
    return ss.priorities is not None


def go(n: int) -> None:
    st.session_state.step = n
    st.query_params["s"] = str(n)
    st.rerun()


def sidebar() -> None:
    ss = st.session_state
    with st.sidebar:
        st.markdown("### 📝 빈틈노트")
        for i, name in enumerate(STEP_NAMES, 1):
            if st.button(name, key=f"nav_{i}", type="primary" if ss.step == i else "secondary",
                         disabled=not step_open(i), width="stretch"):
                go(i)
        st.divider()
        if st.button("처음부터", key="nav_reset", width="stretch"):
            reset_all()
            go(1)
        st.caption(DISCLAIMER)


def current_targets() -> list[str]:
    """진단 대상: 출제 점수 20점 이상 전부(빠른 진단이면 상위 5개). 토글은 위젯의 지금 값으로 센다."""
    ss = st.session_state
    if not ss.scores:
        return []
    all_t = DG.diag_targets(ss.scores)
    quick = ss.get("w_quick", ss.quick_diag)
    if quick and len(all_t) > config.QUICK_DIAG_TOP:
        return DG.diag_targets(ss.scores, top=config.QUICK_DIAG_TOP)
    return all_t


# =========================== S01 ===========================
def page_s01() -> None:
    ss = st.session_state
    st.title("빈틈노트")
    st.markdown('<p class="sub">강의자료와 교수님 녹음 속 강조점, 메타인지 진단으로 시험 전 공부 우선순위를 정해 줍니다.</p>',
                unsafe_allow_html=True)
    st.info(DISCLAIMER)
    if fake_mode():
        st.warning("가짜 AI 모드(BINTM_FAKE_AI=1)예요. 실제 AI 대신 저장된 결과와 정해진 답을 씁니다.")
    if ss.pop("e14", False):
        st.warning(E14 + " (E-14)")
    key_ok = has_llm_key()
    if not key_ok:
        show_error("E-06", "AI 키가 설정되지 않았어요. README의 설정 방법을 보세요")

    up = st.file_uploader(f"강의자료 올리기 (PDF, PPTX · 최대 {config.MAX_MATERIAL_MB}MB)", key="up_material",
                          max_upload_size=config.MAX_MATERIAL_MB)
    if up is not None:
        if XT.ext_of(up.name) not in XT.MATERIAL_EXTS:
            show_error("E-01", XT.E01)
        else:
            st.caption(f"📄 {up.name} · {up.size / 1024 / 1024:.1f}MB")

    t1, t2 = st.tabs(["🎙️ 녹음 파일", "📝 대본 붙여넣기"])
    audio = None
    with t1:
        st.caption("교수님 허락을 받은 녹음만, 개인 학습 목적으로만 올려 주세요.")
        if STT.available():
            audio = st.file_uploader(f"강의 녹음 (m4a, mp3, wav · 최대 {config.MAX_AUDIO_MB}MB)",
                                     type=list(XT.AUDIO_EXTS), key="up_audio", max_upload_size=config.MAX_AUDIO_MB)
        else:
            st.file_uploader(f"강의 녹음 (m4a, mp3, wav · 최대 {config.MAX_AUDIO_MB}MB)", type=list(XT.AUDIO_EXTS),
                             key="up_audio_off", max_upload_size=config.MAX_AUDIO_MB, disabled=True)
            st.caption("음성 인식 키가 없어 녹음 파일을 쓸 수 없어요. 대본 붙여넣기를 써 주세요.")
    with t2:
        paste = st.text_area("받아쓴 대본 (선택)", key="paste_text", height=160,
                             placeholder="휴대폰 녹음 앱의 받아쓰기나 클로바노트 등으로 받아쓴 글을 붙여 넣어 주세요.")
    st.caption("녹음·대본이 없어도 분석할 수 있어요(녹음 신호만 0).")

    c1, c2 = st.columns(2)
    start = c1.button("🔍 분석 시작", type="primary", disabled=(up is None or not key_ok), width="stretch")
    sample = c2.button("🧪 샘플로 체험", disabled=not key_ok, width="stretch",
                       help="우리가 만든 가상 강의자료(자료구조 8장, 20쪽)와 녹음 대본으로 바로 써 봅니다.")
    left = GD.session_left(ss.analyses_used, config.MAX_ANALYSES_PER_SESSION)
    if 0 <= left <= 2:
        st.caption(f"이 화면에서 분석은 {left}번 더 할 수 있어요.")
    st.caption("🔒 " + DATA_NOTICE)

    if start and up is not None:
        run_analysis(up.name, up.getvalue(), paste, audio, from_sample=False)
    elif sample:
        run_analysis(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes(), SAMPLE_TRANSCRIPT.read_text(encoding="utf-8"),
                     None, from_sample=True)
    for code, msg, detail in ss.errors:
        show_error(code, msg, detail)


def run_analysis(name: str, data: bytes, paste: str | None, audio, from_sample: bool) -> None:
    """텍스트 추출 → 녹음 받아쓰기 → 개념 → 강조 → 점수. 알릴 것은 notices에 담아 S02에서 보인다."""
    ss = st.session_state
    ss.errors = []
    blocked = take_analysis()
    if blocked:
        ss.errors = [(blocked, E16 if blocked == "E-16" else E17, None)]
        return
    notices: list[tuple[str, str]] = []
    usage = Usage()
    t0 = time.time()
    try:
        with st.status("분석을 시작해요…", expanded=True) as status:
            status.update(label="텍스트 추출 중…")
            material = XT.extract(name, data)
            if material.get("truncated"):
                notices.append(("E-13", XT.E13))
            transcript, source = None, None
            if paste and paste.strip():
                transcript, source = XT.mask(paste), "paste"  # 대본은 받자마자 가린다
            elif audio is not None:
                status.update(label="녹음 받아쓰는 중…")
                try:
                    XT.check_audio(audio.name, audio.size)
                    transcript, source = XT.mask(STT.transcribe(audio.name, audio.getvalue())), "audio"
                except Exception:
                    notices.append(("E-05", E05))  # 녹음 없이 자동으로 계속
            status.update(label="개념 찾는 중… (보통 30~60초)")
            rid = XT.run_id(data)
            ran: dict = {}
            concepts = cached_concepts(rid, fake_mode(), material, ran)
            usage.merge(ran.get("usage"))
            utter: list = []
            if transcript:
                status.update(label="교수님 강조 찾는 중…")
                ran2: dict = {}
                cj = json.dumps(concepts["concepts"], ensure_ascii=False, sort_keys=True)
                utter = cached_utterances(rid, transcript, cj, fake_mode(), concepts["concepts"], ran2)
                usage.merge(ran2.get("usage"))
                if not utter:
                    notices.append(("E-10", UT.E10))
            status.update(label="점수 계산 중…")
            scores = SC.compute_scores(concepts, utter, material["pages"])
            status.update(label="분석 완료", state="complete", expanded=False)
    except XT.MaterialError as exc:
        give_back_analysis()
        ss.errors = [(exc.code, exc.message, None)]
        return
    except CC.NoConceptsError as exc:
        give_back_analysis()
        ss.errors = [("E-09", str(exc), None)]
        return
    except LLMError as exc:
        give_back_analysis()
        code, msg = error_info(exc)
        ss.errors = [(code, msg, f"{type(exc).__name__}: {exc}")]
        ss.usage.merge(usage)
        return
    except Exception as exc:
        give_back_analysis()
        ss.errors = [(None, UNKNOWN, f"{type(exc).__name__}: {exc}")]
        return

    # 새 분석: 이전 결과를 지우고 채운다 (분석 횟수·사용량은 남김)
    keep = {k: ss[k] for k in ("analyses_used", "usage", "timings") if k in ss}
    for k in list(ss.keys()):
        if not k.startswith(("up_", "paste_")):
            del ss[k]
    init_state()
    for k, v in keep.items():
        ss[k] = v
    ss.usage.merge(usage)
    ss.material = material
    ss.material_bytes = data if material["kind"] == "pdf" else None
    ss.run_id = XT.run_id(data)
    ss.from_sample = from_sample
    ss.transcript, ss.transcript_source = transcript, source
    ss.concepts = concepts["concepts"]
    ss.utterances = utter
    ss.scores = scores["scores"]
    ss.meta_pages = scores["meta_pages"]
    ss.notices = notices
    ss.timings = {**ss.timings, "분석": round(time.time() - t0, 1)}
    go(2)


# =========================== S02 ===========================
def page_s02() -> None:
    ss = st.session_state
    st.header("② 출제 포인트 레이더")
    for code, msg in ss.notices:  # 분석 중에 생긴 안내(E-05·E-10·E-13)
        st.warning(f"{msg} ({code})")
    targets_now = current_targets()
    c1, c2, c3 = st.columns(3)
    c1.metric("찾은 개념", len(ss.concepts))
    c2.metric("교수님 강조", sum(1 for u in ss.utterances if u.get("concept_id")))
    c3.metric("진단할 개념", len(targets_now))
    if not ss.transcript:
        st.info("녹음 없이 자료만으로 계산했어요. 녹음을 넣으면 순위가 더 정확해져요")

    rows, cut_done = [], False
    low = [s for s in ss.scores if s["pct"] < config.DIAG_MIN_PCT]
    for s in ss.scores:
        dim = s["pct"] < config.DIAG_MIN_PCT
        if dim and not cut_done:
            rows.append(f'<div class="cut">아래 {len(low)}개는 출제 가능성 점수가 {config.DIAG_MIN_PCT}점 미만이라 '
                        f"진단하지 않고 '복습만'으로 둬요</div>")
            cut_done = True
        bd = "".join(badge(t, "neg" if neg else "") for t, neg in SC.badges(s))
        rows.append(f'<div class="rank{" dim" if dim else ""}"><span class="no">{s["rank"]}</span>'
                    f'<span class="nm">{esc(s["name"])}</span><span class="bar"><i style="width:{s["pct"]}%"></i></span>'
                    f'<span class="pt">{s["pct"]}점</span><span class="bd">{bd}</span></div>')
    st.html("".join(rows))
    st.caption(SCORE_NOTE)
    st.caption(DISCLAIMER)

    cmap = concept_map()
    with st.expander("점수 내역과 교수님이 한 말 자세히 보기"):
        for s in ss.scores:
            c = cmap.get(s["concept_id"], {})
            parts = [f'<p><b>{s["rank"]}. {esc(s["name"])}</b> · {s["pct"]}점 (원점수 {s["raw"]:g})<br>'
                     f'<span class="info">{esc(c.get("summary"))}</span><br>등장 페이지 '
                     + "".join(f'<span class="pg">p.{n}</span>' for n in s["pages"]) + "</p><ul>"]
            for r in s["reasons"]:
                parts.append(f'<li>{esc(r["label"])} : {r["points"]:+.2f}</li>')
            parts.append("</ul>")
            if c.get("objective_quote"):
                parts.append(f'<p class="info">학습목표: “{esc(c["objective_quote"])}”</p>')
            st.html("".join(parts))
        outside = [u for u in ss.utterances if not u.get("concept_id")]
        if outside:
            st.html("<p><b>개념 목록 밖 언급</b></p><ul>" + "".join(
                f'<li>{esc(u["concept_name"])}: “{esc(u["quote"])}” ({esc(SC.TYPE_LABEL.get(u["type"], u["type"]))})</li>'
                for u in outside) + "</ul>")

    st.subheader("진단 준비")
    locked = bool(ss.grading)
    kw = {} if "w_q_mode" in ss else {"index": DG.MODES.index(ss.q_mode)}
    ss.q_mode = st.radio("문제 형식", DG.MODES, key="w_q_mode", horizontal=True, disabled=locked,
                         help=f"섞어서: 출제 점수 {config.ESSAY_MIN_PCT}점 이상은 서술형, 나머지는 객관식", **kw)
    all_t = DG.diag_targets(ss.scores)
    if len(all_t) > config.QUICK_DIAG_TOP:
        kw = {} if "w_quick" in ss else {"value": ss.quick_diag}
        rest = len(all_t) - config.QUICK_DIAG_TOP
        ss.quick_diag = st.toggle(
            f"빠른 진단: 출제 가능성 상위 {config.QUICK_DIAG_TOP}개만 풀기", key="w_quick", disabled=locked,
            help=f"{len(all_t)}문제 대신 {config.QUICK_DIAG_TOP}문제만 풀어요. 나머지 {rest}개는 '진단 안 함'"
                 f"(이해도 0.5)으로 공부 순서를 계산해요.", **kw)
    if locked:
        st.caption("이미 채점했어요. 문제 형식과 빠른 진단은 바꿀 수 없어요.")
    n = len(current_targets())
    if st.button(f"📝 {n}개 개념 진단하기", type="primary", disabled=n == 0):
        go(3)


# =========================== S03 ===========================
def q_key(cid: str, kind: str) -> str:
    return f"{cid}|{kind}"


def ensure_questions(targets: list[str]) -> None:
    """고른 형식의 문제가 없으면 만든다(동시 호출). 샘플 자료는 서버 공용 저장소에서 꺼내 다시 쓴다."""
    ss = st.session_state
    cmap, smap = concept_map(), score_map()
    names = [cmap[c]["name"] for c in targets]
    jobs = []
    for cid in targets:
        kind = DG.question_kind(smap[cid]["pct"], ss.q_mode)
        k = q_key(cid, kind)
        if k in ss.q_store or k in ss.q_fail:
            continue
        c = cmap[cid]
        pages = DG.evidence_pages(c, ss.material, ss.meta_pages)
        others = DG.other_concepts_text(names, c["name"])
        ckey = (ss.run_id, c["name"], kind, others) if ss.from_sample else None
        cache = sample_cache() if ss.from_sample else None
        if cache is not None:  # 빈 저장소도 거짓이 아니게 'is not None'으로
            hit = cache.get(ckey)
            if hit is not None:
                ss.q_store[k] = hit
                continue
        jobs.append((k, c["name"], kind, pages, others, ckey))
    if not jobs:
        return
    t0 = time.time()
    with st.spinner(f"진단 문제 {len(jobs)}개를 만드는 중이에요… (보통 20~40초)"):
        results = run_parallel(jobs, lambda j, u: DG.make_question(j[1], j[2], j[3], j[4], u), config.PARALLEL_DIAG)
    for job, (ok, val, u) in zip(jobs, results):
        ss.usage.merge(u)
        if ok:
            ss.q_store[job[0]] = val
            if job[5] is not None:
                sample_cache().put(job[5], val)
        else:
            ss.q_fail[job[0]] = (*error_info(val), f"{type(val).__name__}: {val}")
    ss.timings = {**ss.timings, "문제 만들기": round(time.time() - t0, 1)}


def cur_answer(cid):
    ss = st.session_state
    return ss.get(f"ans_{cid}", ss.answers.get(cid, ""))


def cur_dk(cid):
    ss = st.session_state
    return ss.get(f"dk_{cid}", ss.dont_know.get(cid, False))


def cur_choice(cid):
    ss = st.session_state
    return ss.get(f"mcq_{cid}", ss.mcq_choice.get(cid))


def cur_guess(cid):
    ss = st.session_state
    return bool(ss.get(f"guess_{cid}", ss.guessed.get(cid, False)))


def cur_conf(cid):
    ss = st.session_state
    return ss.get(f"conf_{cid}", ss.confusion.get(cid, "")) or ""


def answered(cid: str, q: dict) -> bool:
    return DG.is_answered(q, cur_answer(cid), cur_dk(cid), cur_choice(cid))


def effective_confusion() -> dict:
    """보기를 고르고 '확신 없이 골랐어요'를 체크했을 때 적은 헷갈린 점만."""
    ss = st.session_state
    out = {}
    for cid, q in ss.questions.items():
        if q["kind"] != DG.MCQ:
            continue
        ch = ss.mcq_choice.get(cid)
        if isinstance(ch, int) and ch >= 0 and ss.guessed.get(cid) and (ss.confusion.get(cid) or "").strip():
            out[cid] = ss.confusion[cid].strip()
    return out


def fill_examples() -> None:
    """'예시 답 채우기': 입력칸이 그려지기 전에(콜백에서) 세션 키에 넣는다."""
    ss = st.session_state
    for cid, a in DG.example_answers(ss.questions).items():
        if cid in ss.grading:
            continue
        if ss.questions[cid]["kind"] == DG.ESSAY:
            ss[f"ans_{cid}"], ss[f"dk_{cid}"] = a["answer"], a["dont_know"]
            ss.answers[cid], ss.dont_know[cid] = a["answer"], a["dont_know"]
        else:
            ss[f"mcq_{cid}"], ss[f"guess_{cid}"], ss[f"conf_{cid}"] = a["mcq_choice"], a["guessed"], a["confusion"]
            ss.mcq_choice[cid], ss.guessed[cid], ss.confusion[cid] = a["mcq_choice"], a["guessed"], a["confusion"]
    ss.show_missing = False


def grade_now(targets: list[str]) -> None:
    """모든 문제에 답해야 채점. 객관식·'모르겠어요'는 코드, 서술형은 AI(동시). 실패한 문제만 다시."""
    ss = st.session_state
    qs = ss.questions
    todo = [cid for cid in targets if cid in qs and cid not in ss.grading]
    if any(not DG.is_answered(qs[c], ss.answers.get(c, ""), ss.dont_know.get(c, False), ss.mcq_choice.get(c))
           for c in todo):
        ss.show_missing = True
        return
    ss.show_missing = False
    cmap = concept_map()
    jobs = []
    for cid in todo:
        q = qs[cid]
        if q["kind"] == DG.MCQ:
            ss.grading[cid] = DG.grade_mcq(q, ss.mcq_choice.get(cid), ss.guessed.get(cid, False))
        elif ss.dont_know.get(cid):
            ss.grading[cid] = DG.blank_grading(DG.REASON_DONT_KNOW)
        elif not (ss.answers.get(cid) or "").strip():
            ss.grading[cid] = DG.blank_grading(DG.REASON_EMPTY)
        else:
            c = cmap[cid]
            jobs.append((cid, c["name"], q, ss.answers[cid], DG.evidence_pages(c, ss.material, ss.meta_pages)))
    failed, first_err = [], None
    if jobs:
        t0 = time.time()
        with st.spinner(f"서술형 {len(jobs)}문제를 채점하는 중이에요…"):
            results = run_parallel(jobs, lambda j, u: DG.grade_essay(j[1], j[2], j[3], j[4], u), config.PARALLEL_DIAG)
        for job, (ok, val, u) in zip(jobs, results):
            ss.usage.merge(u)
            if ok:
                ss.grading[job[0]] = val
            else:
                failed.append(job[0])
                first_err = first_err or val
        ss.timings = {**ss.timings, "채점": round(time.time() - t0, 1)}
    ss.grade_failed = failed
    ss.grade_error = None
    if first_err is not None:
        code, msg = error_info(first_err)
        ss.grade_error = (code, msg, f"{type(first_err).__name__}: {first_err}")
    st.rerun()


def go_study() -> None:
    ss = st.session_state
    ss.priorities = PR.compute_priorities(ss.scores, ss.grading)
    ss.auto_done = False
    go(4)


def result_html(q: dict, g: dict, cid: str) -> str:
    """채점 결과: 상태 배지·점수·이유, 객관식은 정답·내 답 표시와 해설."""
    ss = st.session_state
    et = f" · {esc(g['error_type'])}" if g.get("error_type") else ""
    parts = [f'<div>{status_badge(g["status"])} <b>{g["score"]}/10</b>{et}</div>'
             f'<div class="info">{esc(g.get("reason"))}</div>']
    if q["kind"] == DG.MCQ:
        mine = ss.mcq_choice.get(cid)
        for i, ch in enumerate(q["choices"]):
            if i == q["answer_index"]:
                parts.append(f'<div class="choice correct">{MARKS[i]} {esc(ch)} ✔ 정답{" · 내 답" if mine == i else ""}</div>')
            elif i == mine:
                parts.append(f'<div class="choice mine">{MARKS[i]} {esc(ch)} ✘ 내 답</div>')
        conf = effective_confusion().get(cid)
        if conf:
            parts.append(f'<div class="conf">💬 내가 헷갈린 점: {esc(conf)}</div>')
        parts.append(EP.rich(q.get("explanation")))
        parts.append(f'<div class="info">근거 {EP.page_badges(q.get("source_pages"))}</div>')
    return "".join(parts)


def page_s03() -> None:
    ss = st.session_state
    st.header("③ 내 취약점 진단")
    if not ss.grading:
        ss.diag_ids = current_targets()
    targets = ss.diag_ids
    ensure_questions(targets)
    smap, cmap = score_map(), concept_map()
    qs, failed_names, fail_info = {}, [], None
    for cid in targets:
        k = q_key(cid, DG.question_kind(smap[cid]["pct"], ss.q_mode))
        if k in ss.q_store:
            qs[cid] = ss.q_store[k]
        elif cid in ss.grading and ss.questions.get(cid):
            qs[cid] = ss.questions[cid]
        else:
            failed_names.append(cmap[cid]["name"])
            fail_info = ss.q_fail.get(k, fail_info)
    ss.questions = qs
    ss.q_failed = failed_names
    if failed_names:
        code, msg, detail = fail_info or ("E-08", "", "")
        st.warning(f"문제를 만들지 못해 진단에서 뺀 개념: {', '.join(failed_names)} — {msg} ({code})")
        if st.button("문제 다시 만들기", key="q_retry"):
            for cid in targets:
                ss.q_fail.pop(q_key(cid, DG.question_kind(smap[cid]["pct"], ss.q_mode)), None)
            st.rerun()
    if not qs:
        show_error(fail_info[0] if fail_info else "E-07", "진단 문제를 하나도 만들지 못했어요. 잠시 후 '문제 다시 만들기'를 눌러 주세요",
                   fail_info[2] if fail_info else None)
        return

    order = [c for c in targets if c in qs]
    n_mcq = sum(1 for c in order if qs[c]["kind"] == DG.MCQ)
    graded_all = all(c in ss.grading for c in order)
    if graded_all:
        stc = {s: sum(1 for c in order if ss.grading[c]["status"] == s) for s in ("앎", "헷갈림", "모름")}
        m1, m2, m3 = st.columns(3)
        m1.metric("앎", stc["앎"])
        m2.metric("헷갈림", stc["헷갈림"])
        m3.metric("모름", stc["모름"])
    done = sum(1 for c in order if answered(c, qs[c]))
    st.progress(done / len(order), text=f"답한 문제 {done} / {len(order)} · 객관식 {n_mcq} · 서술형 {len(order) - n_mcq}")
    if ss.from_sample and done < len(order) and not graded_all:
        st.caption("샘플로 둘러보는 중이라면 '예시 답 채우기'로 바로 채점까지 가 볼 수 있어요.")
        st.button("예시 답 채우기 (샘플 체험용)", key="fill_ex", on_click=fill_examples)
    if ss.grade_failed:
        code, msg, detail = ss.grade_error or ("E-08", "AI 답을 읽지 못했어요. 다시 시도해 주세요", None)
        show_error(code, f"서술형 {len(ss.grade_failed)}문제를 채점하지 못했어요. {msg}", detail)

    for i, cid in enumerate(order, 1):
        q = qs[cid]
        locked = cid in ss.grading
        with st.container(border=True):
            st.html(f'<div><b>Q{i}. {esc(cmap[cid]["name"])}</b> {badge(q["kind"], "kind")}'
                    f'{badge("출제 점수 " + str(smap[cid]["pct"]))}</div>'
                    f'<div class="qtext">{esc(q["question"])}</div>{figure_html(q.get("figure"))}')
            if q["kind"] == DG.ESSAY:
                kw = {} if f"ans_{cid}" in ss else {"value": ss.answers.get(cid, "")}
                ss.answers[cid] = st.text_area("내 답", key=f"ans_{cid}", height=110, disabled=locked,
                                               placeholder="아는 만큼 2~3문장으로 적어 주세요.", **kw)
                kw = {} if f"dk_{cid}" in ss else {"value": ss.dont_know.get(cid, False)}
                ss.dont_know[cid] = st.checkbox("모르겠어요", key=f"dk_{cid}", disabled=locked, **kw)
            else:
                opts = [0, 1, 2, 3, -1]
                prev = ss.mcq_choice.get(cid)
                kw = {} if f"mcq_{cid}" in ss else {"index": opts.index(prev) if prev in opts else None}
                ss.mcq_choice[cid] = st.radio(
                    "보기 고르기", opts, key=f"mcq_{cid}", disabled=locked, label_visibility="collapsed",
                    format_func=lambda o, q=q: "모르겠어요" if o == -1 else f"{MARKS[o]} {md_safe(q['choices'][o])}", **kw)
                ch = ss.mcq_choice[cid]
                if isinstance(ch, int) and ch >= 0:
                    kw = {} if f"guess_{cid}" in ss else {"value": ss.guessed.get(cid, False)}
                    ss.guessed[cid] = st.checkbox("확신 없이 골랐어요 (찍었어요)", key=f"guess_{cid}", disabled=locked, **kw)
                    if ss.guessed[cid]:
                        kw = {} if f"conf_{cid}" in ss else {"value": ss.confusion.get(cid, "")}
                        ss.confusion[cid] = st.text_area(
                            "어떤 점이 헷갈렸나요? (선택)", key=f"conf_{cid}", max_chars=config.CONFUSION_MAX_CHARS,
                            height=80, disabled=locked,
                            placeholder="예: ②와 ③ 중에 고민했어요. 두 방법이 어떻게 다른지 모르겠어요.", **kw)
            if ss.show_missing and not locked and not answered(cid, q):
                st.html(f'<div class="missing">{E11_CARD}</div>')
            if cid in ss.grade_failed:
                st.html('<div class="failtxt">이 문제는 채점하지 못했어요. 답은 그대로 두고 아래 버튼으로 다시 채점해 주세요.</div>')
            if locked:
                st.html(result_html(q, ss.grading[cid], cid))
                if q["kind"] == DG.ESSAY:
                    with st.expander("모범 답안과 채점 기준"):
                        rs = ss.grading[cid].get("rubric_scores") or []
                        rub = "".join(
                            f"<li>{esc(r['point'])}: {rs[j] if j < len(rs) else '-'} / {r['score']}점</li>"
                            for j, r in enumerate(q.get("rubric", [])))
                        st.html(EP.rich(q.get("answer")) + f"<ul>{rub}</ul>"
                                + f'<div class="info">근거 {EP.page_badges(q.get("source_pages"))}</div>')

    if not graded_all:
        st.caption("모든 문제에 답해야 채점해요. 모르면 '모르겠어요'를 고르면 돼요.")
        label = "채점 못한 문제 다시 채점" if ss.grade_failed else "✅ 채점하기"
        if st.button(label, type="primary", key="grade_btn"):
            grade_now(order)
        if ss.show_missing:
            miss = [f"Q{i}" for i, c in enumerate(order, 1) if c not in ss.grading and not answered(c, qs[c])]
            if miss:
                st.html(f'<div class="missing">아직 답하지 않은 문제: {", ".join(miss)}</div>')
        if ss.grade_failed and st.button("채점 못한 문제는 빼고 공부 순서 보기", key="skip_failed"):
            go_study()
    else:
        if st.button("📚 공부 순서 보기", type="primary", key="to_study"):
            go_study()


# =========================== S04 ===========================
def export_state() -> dict:
    ss = st.session_state
    return dict(material=ss.material, transcript_source=ss.transcript_source, scores=ss.scores,
                priorities=ss.priorities, questions=ss.questions, grading=ss.grading, answers=ss.answers,
                dont_know=ss.dont_know, mcq_choice=ss.mcq_choice, guessed=ss.guessed,
                confusion=effective_confusion(), explanations=ss.explanations, notes=ss.notes,
                concepts=ss.concepts, utterances=ss.utterances, meta_pages=ss.meta_pages)


def explain_job(cid: str) -> tuple:
    """스레드에 넘길 값은 스레드를 만들기 전에 세션에서 꺼내 둔다."""
    ss = st.session_state
    c = concept_map()[cid]
    p = next(x for x in ss.priorities if x["concept_id"] == cid)
    my = {"answer": ss.answers.get(cid, ""), "dont_know": ss.dont_know.get(cid, False),
          "mcq_choice": ss.mcq_choice.get(cid), "guessed": ss.guessed.get(cid, False)}
    q = ss.questions.get(cid) if cid in ss.grading else None
    return ("x", cid, c["name"], p["status"], q, ss.grading.get(cid), my,
            effective_confusion().get(cid, ""), DG.evidence_pages(c, ss.material, ss.meta_pages))


def note_job(cid: str, detail: str) -> tuple:
    ss = st.session_state
    c = concept_map()[cid]
    p = next(x for x in ss.priorities if x["concept_id"] == cid)
    info = {"exam_pct": p["exam_pct"], "action": p["action"], "status": p["status"], "grading": ss.grading.get(cid)}
    return ("n", cid, c, detail, info, list(ss.utterances), DG.evidence_pages(c, ss.material, ss.meta_pages))


def _do_job(job: tuple, u: Usage):
    if job[0] == "x":
        _, cid, name, status, q, g, my, conf, pages = job
        return EX.make_explanation(cid, name, status, q, g, my, conf, pages, u)
    _, cid, c, detail, info, utter, pages = job
    return NT.make_note(c, detail, info, utter, pages, u)


def run_study_jobs(jobs: list, label: str) -> None:
    ss = st.session_state
    if not jobs:
        return
    t0 = time.time()
    with st.spinner(label):
        results = run_parallel(jobs, _do_job, config.PARALLEL_STUDY)
    for job, (ok, val, u) in zip(jobs, results):
        ss.usage.merge(u)
        cid = job[1]
        if job[0] == "x":
            if ok:
                ss.explanations[cid] = val
                ss.explain_failed = [x for x in ss.explain_failed if x != cid]
            elif cid not in ss.explain_failed:
                ss.explain_failed.append(cid)
        else:
            if ok:
                ss.notes[cid] = val
                ss.notes_failed = [x for x in ss.notes_failed if x != cid]
            elif cid not in ss.notes_failed:
                ss.notes_failed.append(cid)
        if not ok:
            ss.item_errors[f"{job[0]}:{cid}"] = (*error_info(val), f"{type(val).__name__}: {val}")
    ss.timings = {**ss.timings, "④ 설명·노트": round(time.time() - t0, 1)}


def auto_generate() -> None:
    """S04가 열릴 때: '지금 당장' 전부·상위 3개·헷갈린 점을 적은 개념의 설명 + '자세히'·'보통' 요약 노트(동시)."""
    ss = st.session_state
    cmap = concept_map()
    expl = [cid for cid in EX.auto_targets(ss.priorities, effective_confusion())
            if cid not in ss.explanations and cid not in ss.explain_failed]
    jobs = [explain_job(cid) for cid in expl]
    n_note = 0
    for cid, detail in NT.note_plan(ss.concepts, ss.priorities, ss.meta_pages):
        if detail == NT.SHORT:
            ss.notes.setdefault(cid, NT.short_note(cmap[cid], ss.meta_pages))  # AI 호출 없음
        elif cid not in ss.notes and cid not in ss.notes_failed:
            jobs.append(note_job(cid, detail))
            n_note += 1
    run_study_jobs(jobs, f"보완 설명 {len(expl)}개와 요약 노트 {n_note}개를 만드는 중이에요… (보통 20~40초)")


def page_images(cid: str, pages: list[int]) -> None:
    ss = st.session_state
    pages = [p for p in pages if isinstance(p, int)][:2]
    if not ss.material_bytes or not pages:
        return
    with st.expander("강의자료 원본 보기 · " + ", ".join(f"p.{p}" for p in pages)):
        for p in pages:
            img = cached_page_img(ss.run_id, p, ss.material_bytes)
            if img:
                st.image(img, caption=f"p.{p}")


def study_card(p: dict, est: dict) -> None:
    ss = st.session_state
    cid = p["concept_id"]
    smap = score_map()
    with st.container(border=True):
        st.html(f'<div><b>{p["rank"]}. {esc(p["name"])}</b> {status_badge(p["status"])}'
                f'{badge("출제 점수 " + str(p["exam_pct"]))}{badge("우선순위 " + str(p["priority"]))}</div>')
        q, g = ss.questions.get(cid), ss.grading.get(cid)
        if q and g:
            with st.expander(f"📝 내 문제와 답 다시 보기 · {g['status']} {g['score']}/10"):
                st.html(EP._question_block(q, est, cid, g))
        e = ss.explanations.get(cid)
        if e:
            st.html(EP.explanation_block(e, est["confusion"].get(cid, "")))
        elif cid in ss.explain_failed:
            code, msg, detail = ss.item_errors.get(f"x:{cid}", ("E-08", "AI 답을 읽지 못했어요.", None))
            st.html(f'<div class="failtxt">설명을 만들지 못했어요. {esc(msg)} ({esc(code)})</div>')
            if st.button("설명 다시 만들기", key=f"rex_{cid}"):
                run_study_jobs([explain_job(cid)], "설명을 다시 만드는 중이에요…")
                st.rerun()
        else:
            if st.button("설명 보기", key=f"ex_{cid}"):
                run_study_jobs([explain_job(cid)], "설명을 만드는 중이에요…")
                st.rerun()
        pages = (e or {}).get("check_pages") or smap.get(cid, {}).get("body_pages") or smap.get(cid, {}).get("pages", [])
        page_images(cid, pages)


def note_card(i: int, cid: str, detail: str) -> None:
    ss = st.session_state
    c = concept_map()[cid]
    p = next(x for x in ss.priorities if x["concept_id"] == cid)
    n = ss.notes.get(cid)
    with st.container(border=True):
        st.html(f'<div><b>{i}. {esc(c["name"])}</b> {badge(detail, "kind")}{badge("출제 점수 " + str(p["exam_pct"]))}'
                f'{status_badge(p["status"])}</div>')
        if n:
            parts = [EP.rich(n.get("summary"))]
            if n.get("key_points"):
                parts.append("<b>핵심</b><ul>" + "".join(f"<li>{EP.rich(k)[3:-4]}</li>" for k in n["key_points"]) + "</ul>")
            if n.get("pitfalls"):
                parts.append("<b>자주 하는 실수</b><ul>" + "".join(f"<li>{EP.rich(k)[3:-4]}</li>" for k in n["pitfalls"]) + "</ul>")
            quotes = NT.professor_quotes(cid, ss.utterances)
            if quotes:
                parts.append("<b>교수님 말</b><ul>" + "".join(
                    f"<li>“{esc(q['quote'])}” {badge(SC.TYPE_LABEL.get(q['type'], q['type']))}</li>" for q in quotes) + "</ul>")
            parts.append(f'<div class="info">근거 {EP.page_badges(n.get("source_pages"))}</div>')
            st.html("".join(parts))
        elif cid in ss.notes_failed:
            code, msg, detail_ = ss.item_errors.get(f"n:{cid}", ("E-08", "AI 답을 읽지 못했어요.", None))
            st.html(f'<div class="failtxt">요약 노트를 만들지 못했어요. {esc(msg)} ({esc(code)})</div>')
            if st.button("요약 노트 다시 만들기", key=f"rnote_{cid}"):
                run_study_jobs([note_job(cid, detail)], "요약 노트를 다시 만드는 중이에요…")
                st.rerun()
        page_images(cid, (n or {}).get("source_pages") or c.get("pages", []))


def downloads(where: str, est: dict) -> None:
    f1, f2 = EP.file_names()
    c1, c2 = st.columns(2)
    c1.download_button("📥 공부 순서·오답노트 내려받기", data=EP.study_html(est).encode("utf-8"), file_name=f1,
                       mime="text/html", key=f"dl_study_{where}", width="stretch")
    c2.download_button("📒 요약 노트 내려받기", data=EP.notes_html(est).encode("utf-8"), file_name=f2,
                       mime="text/html", key=f"dl_notes_{where}", width="stretch")


def page_s04() -> None:
    ss = st.session_state
    st.header("④ 우선순위 보완 학습")
    if not ss.auto_done:
        auto_generate()
        ss.auto_done = True
    groups = PR.group(ss.priorities)
    c1, c2, c3 = st.columns(3)
    c1.metric("지금 당장", len(groups[PR.NOW]))
    c2.metric("다음", len(groups[PR.NEXT]))
    c3.metric("복습만", len(groups[PR.REVIEW]))
    est = export_state()
    downloads("top", est)
    tab1, tab2 = st.tabs(["🎯 공부 순서와 오답노트", "📒 시험 대비 요약 노트"])
    with tab1:
        st.markdown("#### 🔴 지금 당장 · 여기부터 보세요")
        st.caption("출제 가능성이 높은데 아직 모르는 개념이에요.")
        if not groups[PR.NOW]:
            st.caption("없어요.")
        for p in groups[PR.NOW]:
            study_card(p, est)
        st.markdown("#### 🟡 다음")
        st.caption("지금 당장 다음으로 볼 개념이에요.")
        missing = [p["concept_id"] for p in groups[PR.NEXT]
                   if p["concept_id"] not in ss.explanations and p["concept_id"] not in ss.explain_failed]
        if missing and st.button(f"'다음' 개념 설명 {len(missing)}개 한 번에 보기", key="next_all"):
            run_study_jobs([explain_job(c) for c in missing], f"설명 {len(missing)}개를 만드는 중이에요…")
            st.rerun()
        if not groups[PR.NEXT]:
            st.caption("없어요.")
        for p in groups[PR.NEXT]:
            study_card(p, est)
        st.markdown("#### 🟢 복습만")
        st.caption("'진단 안 함'은 출제 가능성 점수가 20점 미만이라 문제를 내지 않은 개념이에요. 이미 아는 개념도 여기에 있어요.")
        shown, folded = PR.split_review(groups[PR.REVIEW], est["confusion"])
        for p in shown:  # 헷갈린 점을 적은 개념은 접지 않는다
            study_card(p, est)
        if folded:
            with st.expander(f"복습만 {len(folded)}개 펼치기"):
                for p in folded:
                    study_card(p, est)
        with st.expander("전체 표로 보기"):
            rows = "".join(
                f'<tr><td>{p["rank"]}</td><td style="text-align:left">{esc(p["name"])}</td>'
                f'<td><span class="mini"><i style="width:{p["exam_pct"]}%"></i></span>{p["exam_pct"]}점</td>'
                f'<td>{esc(p["status"])}</td><td><span class="mini"><i style="width:{p["priority"]}%"></i></span>'
                f'{p["priority"]}</td><td>{esc(p["action"])}</td></tr>' for p in ss.priorities)
            st.html('<table class="tbl"><tr><th>순위</th><th>개념</th><th>출제 점수</th><th>이해 상태</th>'
                    f'<th>우선순위</th><th>권장</th></tr>{rows}</table><p class="info">{esc(EP.FORMULA)}</p>')
    with tab2:
        st.caption("강의 순서대로 모든 개념을 정리했어요. 중요한 개념일수록 자세히 썼어요.")
        for i, (cid, detail) in enumerate(NT.note_plan(ss.concepts, ss.priorities, ss.meta_pages), 1):
            note_card(i, cid, detail)
    st.divider()
    downloads("bottom", export_state())
    if st.button("🔄 다른 자료로 다시", key="restart"):
        reset_all()
        go(1)


# =========================== S05 ===========================
def page_s05() -> None:
    ss = st.session_state
    st.header("⑤ 안내·설정")
    st.markdown("**사용 방법**\n1. ① 강의자료(PDF/PPTX)와 녹음 또는 대본을 올리고 분석을 시작합니다.\n"
                "2. ② 출제 가능성 순위와 근거를 봅니다.\n3. ③ 진단 문제를 풀고 채점합니다.\n"
                "4. ④ 공부 순서·오답노트와 시험 대비 요약 노트를 보고 HTML로 내려받습니다.")
    st.warning(DISCLAIMER + " 녹음은 교수님 허락을 받은 것만, 개인 학습 목적으로만 올려 주세요.")
    st.caption(DATA_NOTICE)
    u = ss.usage
    rows = [("언어 모델", config.LLM_MODEL), ("음성 인식", "사용 가능" if STT.available() else "꺼짐(대본 붙여넣기만)"),
            ("진단 기준", f"출제 가능성 점수 {config.DIAG_MIN_PCT}점 이상 전부"), ("문제 형식", ss.q_mode),
            ("가중치 버전", SC.WEIGHT_VERSION),
            ("이번 세션 사용량", f"AI 호출 {u.calls}번 · 입력 {u.input_tokens:,} · 출력 {u.output_tokens:,} 토큰"),
            ("분석 횟수", f"이 화면 {ss.analyses_used} / {config.MAX_ANALYSES_PER_SESSION}번")]
    if ss.timings:
        rows.append(("단계별 시간", " · ".join(f"{k} {v}초" for k, v in ss.timings.items())))
    st.html('<table class="tbl">' + "".join(f'<tr><th style="text-align:left">{esc(a)}</th>'
                                            f'<td style="text-align:left">{esc(b)}</td></tr>' for a, b in rows) + "</table>")
    st.caption("AI 호출 수는 호출마다 셉니다. 저장된 결과를 다시 쓰면 AI를 부르지 않으므로 더하지 않습니다.")
    st.markdown(f"**정보** · 팀 빈틈노트 · KOREATECH AI 실습형 이벤트 Build for Students · [GitHub 저장소]({REPO_URL})")


# =========================== 실행 ===========================
def main() -> None:
    init_state()
    _load_keys()
    st.markdown(CSS, unsafe_allow_html=True)
    ss = st.session_state
    # 새로고침으로 세션이 사라졌으면 S01으로 (E-14)
    try:
        qp = int(st.query_params.get("s", "1"))
    except ValueError:
        qp = 1
    if qp > 1 and ss.material is None and ss.step == 1 and not ss.get("e14_seen"):
        ss.e14 = True
        ss.e14_seen = True
        st.query_params["s"] = "1"
    if not step_open(ss.step):
        ss.step = 1
    sidebar()
    stepper(min(ss.step, 4) if ss.step != 5 else 0)
    try:
        {1: page_s01, 2: page_s02, 3: page_s03, 4: page_s04, 5: page_s05}[ss.step]()
    except Exception as exc:
        show_error(None, UNKNOWN, f"{type(exc).__name__}: {exc}")


main()
