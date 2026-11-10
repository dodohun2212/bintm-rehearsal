"""S01 자료 올리기: 업로드 2종, 대본 붙여넣기, 샘플 체험, 진행 표시, 분석."""
from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

import config
from core import diagnose, guard, llm, score, stt
from core.concepts import NoConceptsError, concepts_for_prompt, extract_concepts
from core.extract import ScannedPdfError, UnsupportedFileError, check_audio, check_material, extract, mask, run_id_of
from core.utterances import find_utterances
from screens import common as C

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_TRANSCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"


@st.cache_data(show_spinner=False, max_entries=50)
def cached_concepts(run_id: str, _material: dict, _sink: dict) -> dict:
    """호출 1 결과를 같은 파일(run_id)이면 다시 쓴다. 실제로 부른 때만 _sink에 사용량을 남긴다."""
    usage = llm.Usage()
    _sink["usage"] = usage
    return extract_concepts(_material, usage)


@st.cache_data(show_spinner=False, max_entries=50)
def cached_utterances(run_id: str, transcript: str, concepts_json: str, _concepts: list, _sink: dict) -> list:
    """호출 2 캐시. 키에 대본과 개념 목록(JSON)을 함께 넣는다."""
    usage = llm.Usage()
    _sink["usage"] = usage
    return find_utterances(transcript, _concepts, usage)


def run_analysis(name: str, data: bytes, transcript: str | None, source: str | None,
                 audio: tuple[str, bytes] | None, from_sample: bool) -> None:
    code = C.take_analysis()
    if code:
        C.show_error(code)
        return
    started = time.perf_counter()
    sinks: list[dict] = [{}, {}]
    notices: list[str] = []
    ai_called = False
    try:
        with st.status("분석하는 중이에요…", expanded=True) as status:
            status.write("텍스트 추출 중")
            material = extract(name, data)
            if material["orig_pages"] > config.MAX_PAGES:
                notices.append(f"{C.ERRORS['E-13']} (E-13)")
            if audio and not transcript:
                status.write("녹음 받아쓰는 중")
                ai_called = True  # 받아쓰기도 외부 AI 호출이다
                try:
                    transcript = stt.transcribe(*audio)
                    source = "audio"
                except stt.SttError:
                    notices.append(f"{C.ERRORS['E-05']} (E-05)")
                    transcript, source = None, None
            transcript = mask(transcript) if transcript else None  # 대본은 받자마자 가린다
            run_id = run_id_of(data, transcript or "")
            status.write("개념 찾는 중")
            ai_called = True
            concepts = cached_concepts(run_id_of(data), material, sinks[0])
            status.write("교수님 강조 찾는 중")
            utts = []
            if transcript:
                utts = cached_utterances(run_id, transcript, concepts_for_prompt(concepts["concepts"]),
                                         concepts["concepts"], sinks[1])
                if not utts:
                    notices.append(f"{C.ERRORS['E-10']} (E-10)")
            status.write("점수 계산 중")
            meta = score.meta_pages(material["pages"], concepts)
            scores = score.compute_scores(concepts["concepts"], utts, meta)["scores"]
            status.update(label="분석이 끝났어요", state="complete")
    except Exception as exc:
        calls = _account(sinks, started)
        _refund(True, ai_called, calls)
        if isinstance(exc, ScannedPdfError):
            C.show_error("E-03")
        elif isinstance(exc, UnsupportedFileError):
            C.show_error("E-01")
        elif isinstance(exc, NoConceptsError):
            C.show_error("E-09")
        else:  # AI 호출 실패 등
            C.show_error(C.error_code(exc), f"{type(exc).__name__}: {exc}")
        return
    _refund(False, ai_called, _account(sinks, started))
    C.clear_after_analysis()
    targets = diagnose.diag_targets(scores)
    st.session_state.update(
        material=material, material_bytes=data if material["kind"] == "pdf" else None,
        transcript=transcript, transcript_source=source if transcript else None,
        concepts=concepts["concepts"], meta_pages=meta, utterances=utts, scores=scores,
        run_id=run_id, from_sample=from_sample, q_mode="섞어서",
        quick_diag=diagnose.quick_default(len(targets), from_sample), notices=notices, step=2,
    )
    st.rerun()


def _refund(failed: bool, ai_called: bool, calls: int) -> None:
    """AI를 부르기 전 실패는 둘 다, 저장된 결과만 쓴 분석은 하루 횟수만 돌려준다(guard.refund)."""
    session_back, daily_back = guard.refund(failed, ai_called, calls)
    if session_back:
        C.give_back_analysis()
    elif daily_back:
        C.give_back_daily_only()


def _account(sinks: list[dict], started: float) -> int:
    """실제로 부른 호출만 사용량에 더한다. 돌려주는 값은 이번 분석의 AI 호출 수."""
    total = llm.Usage()
    for sink in sinks:
        total.merge(sink.get("usage"))
    C.add_usage(total, "분석", time.perf_counter() - started)
    return total.calls


def render() -> None:
    C.header(1, "빈틈노트", "강의자료와 교수님 녹음에서 출제 신호를 모으고, 진단 문제로 내 빈틈을 찾아 시험 전 공부 순서를 정해 줘요.")
    st.info(C.DISCLAIMER)
    if llm.fake_mode():
        st.warning("가짜 AI 모드예요(BINTM_FAKE_AI=1). 실제 AI 대신 저장된 답으로 화면만 확인해요.")
    has_key = llm.has_llm_key()
    if not has_key:
        C.show_error("E-06")

    material_file = st.file_uploader("강의자료 (PDF, PPTX · 최대 30MB)", type=["pdf", "pptx"], key="up_material")
    if material_file is not None:
        err = check_material(material_file.name, material_file.size)
        if err:
            C.show_error(err)
            material_file = None

    tab_audio, tab_paste = st.tabs(["🎙️ 녹음 파일", "📝 대본 붙여넣기"])
    audio = None
    with tab_audio:
        st.caption("교수님 허락을 받은 녹음만, 개인 학습 목적으로만 올려 주세요.")
        stt_ok = stt.available() and not llm.fake_mode()
        audio_file = st.file_uploader("강의 녹음 (m4a, mp3, wav · 최대 25MB)", type=["m4a", "mp3", "wav"],
                                      key="up_audio", disabled=not stt_ok, max_upload_size=config.MAX_AUDIO_MB)
        if not stt_ok:
            st.caption("음성 인식 키가 없어 녹음 받아쓰기를 쓸 수 없어요. 대본 붙여넣기를 써 주세요.")
        if audio_file is not None:
            if check_audio(audio_file.name, audio_file.size):
                C.show_error("E-04")
            else:
                audio = (audio_file.name, audio_file.getvalue())
    with tab_paste:
        st.caption("받아쓰기 앱(예: 클로바노트)으로 만든 대본을 붙여 넣어도 돼요. 녹음 파일과 둘 다 있으면 대본을 써요.")
        paste = st.text_area("대본", key="paste_text", height=160, placeholder="강의 대본을 붙여 넣으세요")

    col1, col2 = st.columns(2)
    start = col1.button("분석 시작", type="primary", disabled=material_file is None or not has_key, width="stretch")
    sample = col2.button("🧪 샘플로 체험", disabled=not has_key, width="stretch",
                         help="직접 만든 가상 강의자료(자료구조 8장, 20쪽)와 녹음 대본으로 바로 써 봐요.")
    left = guard.session_left(st.session_state["analyses_used"], config.MAX_ANALYSES_PER_SESSION)
    if 0 <= left <= 2:
        st.caption(f"이 화면에서 분석은 {left}번 더 할 수 있어요.")
    st.caption(C.SEND_NOTICE + " " + C.STORE_NOTICE)
    st.caption(C.ERRORS["E-14"])

    if start and material_file is not None:
        text = (paste or "").strip() or None
        run_analysis(material_file.name, material_file.getvalue(), text, "paste" if text else None,
                     audio, from_sample=False)
    if sample:
        run_analysis(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes(), SAMPLE_TRANSCRIPT.read_text(encoding="utf-8"),
                     "paste", None, from_sample=True)
