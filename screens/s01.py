"""S01 자료 올리기: 업로드 2종 + 대본 붙여넣기 + 샘플 체험 + 분석(진행 표시)."""
from __future__ import annotations

import json
import time
from pathlib import Path

import streamlit as st

import config
from core import llm, stt
from core.concepts import NoConceptError, extract_concepts
from core.extract import ExtractError, extract, mask, run_id_of
from core.guard import refund_needed, session_left
from core.html import DISCLAIMER, esc
from core.score import compute_scores
from core.utterances import find_utterances
from screens.common import (ERR, S, add_usage, clear_results_for_new_analysis, counters, html, show_error,
                            step_bar)

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_PDF = ROOT / "samples" / "자료구조_8장_트리와힙_가상강의자료.pdf"
SAMPLE_SCRIPT = ROOT / "samples" / "강의녹음_대본_8장_트리와힙.md"


@st.cache_data(show_spinner=False, max_entries=50)
def cached_concepts(run_id: str, _material: dict, _holder: dict) -> tuple[dict, dict]:
    """호출 1 결과 캐시(같은 파일이면 다시 쓴다). _holder['ran']으로 실제로 불렀는지 알린다."""
    _holder["ran"] = True
    u = llm.Usage()
    res = extract_concepts(_material, usage=u)
    return res, u.to_dict()


@st.cache_data(show_spinner=False, max_entries=50)
def cached_utterances(run_id: str, transcript: str, concepts_key: str, _concepts: list, _holder: dict):
    """호출 2 결과 캐시. 키에 대본과 개념 목록(JSON)도 넣는다."""
    _holder["ran"] = True
    u = llm.Usage()
    res = find_utterances(transcript, _concepts, usage=u)
    return res, u.to_dict()


def take_analysis() -> bool:
    """분석 1번을 쓴다. 세션 한도면 E-16, 하루 한도면 E-17."""
    if session_left(S["analyses_used"], config.MAX_ANALYSES_PER_SESSION) == 0:
        show_error("E-16")
        return False
    if not counters()["analyses"].try_take():
        show_error("E-17")
        return False
    S["analyses_used"] += 1
    return True


def give_back_analysis(session: bool, daily: bool) -> None:
    if session:
        S["analyses_used"] = max(0, S["analyses_used"] - 1)
    if daily:
        counters()["analyses"].give_back()


def run_analysis(name: str, data: bytes, transcript: str | None, source: str | None, from_sample: bool,
                 audio: tuple[str, bytes] | None = None) -> None:
    """분석 1~7단계. 성공하면 ②로 넘어간다."""
    if not take_analysis():
        return
    if counters()["ai_calls"].exhausted():
        give_back_analysis(True, True)
        show_error("E-17")
        return
    u = llm.Usage()
    notices: list[str] = []
    failed = True
    t_start = time.time()
    try:
        with st.status("분석 중… 보통 30~60초 걸려요", expanded=True) as status:
            st.write("텍스트 추출 중")
            material = extract(name, data)
            if material["original_pages"] > config.MAX_PAGES:
                notices.append(f"{ERR['E-13']} (E-13)")
            if audio and not (transcript or "").strip():
                st.write("녹음 받아쓰는 중")
                try:
                    transcript = stt.transcribe(audio[0], audio[1])
                    source = "audio"
                except stt.STTError as e:
                    notices.append(f"{ERR[e.code]} ({e.code})")
                    transcript, source = None, None
            transcript = mask(transcript) if transcript and transcript.strip() else None
            if not transcript:
                source = None
            run_id = run_id_of(data)
            st.write("개념 찾는 중")
            h1 = {"ran": False}
            t0 = time.time()
            cres, u1 = cached_concepts(run_id, material, h1)
            if h1["ran"]:
                u.merge(llm.Usage.from_dict(u1))
            u.add_stage("① 개념 찾기", time.time() - t0)
            utts = []
            if transcript:
                st.write("교수님 강조 찾는 중")
                h2 = {"ran": False}
                t0 = time.time()
                ckey = json.dumps([(c["id"], c["name"]) for c in cres["concepts"]], ensure_ascii=False)
                utts, u2 = cached_utterances(run_id, transcript, ckey, cres["concepts"], h2)
                if h2["ran"]:
                    u.merge(llm.Usage.from_dict(u2))
                u.add_stage("① 교수님 강조 찾기", time.time() - t0)
                if not utts:
                    notices.append(f"{ERR['E-10']} (E-10)")
            st.write("점수 계산 중")
            scores = compute_scores(cres["concepts"], utts, cres["meta_pages"])
            status.update(label="분석 끝", state="complete")
        failed = False
    except ExtractError as e:
        show_error(e.code, str(e))
    except NoConceptError:
        show_error("E-09")
    except llm.AIError as e:
        show_error(e.code, str(e))
    except Exception as e:  # noqa: BLE001
        show_error("UNKNOWN", f"{type(e).__name__}: {e}")
    finally:
        add_usage(u)
        sess_back, day_back = refund_needed(failed, u.calls)
        give_back_analysis(sess_back, day_back)
    if failed:
        return
    used = S["analyses_used"]
    clear_results_for_new_analysis()
    S["analyses_used"] = used
    total = llm.Usage.from_dict(S["usage"])
    total.merge(llm.Usage(stages={"① 분석 전체": time.time() - t_start}))
    S["usage"] = total.to_dict()
    S.update({"material": material, "material_bytes": data if material["kind"] == "pdf" else None,
              "transcript": transcript, "transcript_source": source, "concepts": cres["concepts"],
              "meta_pages": cres["meta_pages"], "utterances": utts, "scores": scores, "run_id": run_id,
              "from_sample": from_sample, "notices": notices, "step": 2})
    from core.diagnose import diag_targets, quick_default
    S["quick_diag"] = quick_default(len(diag_targets(scores["scores"])), from_sample)
    st.rerun()


def render() -> None:
    step_bar(1)
    st.title("빈틈노트")
    st.write("강의자료와 교수님 강의 녹음(또는 대본)으로 **출제 포인트 순위 → 내 취약점 진단 → 공부 순서와 오답노트 → "
             "시험 대비 요약 노트**를 만들어 드려요.")
    html(f'<div class="bt-warn">⚠️ {esc(DISCLAIMER)}</div>')
    for n in S.get("errors") or []:
        st.warning(n)
    if st.session_state.get("bt_lost"):
        st.info(ERR["E-14"])
    from core import fake_ai
    if fake_ai.enabled():
        st.warning("가짜 AI 모드예요(BINTM_FAKE_AI=1). 실제 AI 대신 저장된 결과와 정해진 답을 씁니다.")
    key_ok = llm.has_key()
    if not key_ok:
        show_error("E-06")

    st.subheader("샘플로 바로 체험하기")
    st.caption("우리 팀이 만든 가상 강의자료(자료구조 8장 트리와 힙, 20쪽)와 강의 대본으로 끝까지 써 볼 수 있어요.")
    if st.button("🧪 샘플 자료로 체험하기", type="primary", disabled=not key_ok, key="bt_sample", width="stretch"):
        run_analysis(SAMPLE_PDF.name, SAMPLE_PDF.read_bytes(), SAMPLE_SCRIPT.read_text(encoding="utf-8"),
                     "paste", True)

    st.subheader("내 자료 올리기")
    up = st.file_uploader("강의자료 (PDF·PPTX, 최대 30MB)", type=["pdf", "pptx"], key="bt_material")
    if up is not None:
        st.caption(f"올린 파일: {up.name} · {up.size / 1024 / 1024:.1f}MB")
    tab_audio, tab_paste = st.tabs(["🎙️ 녹음 파일", "📝 대본 붙여넣기"])
    with tab_audio:
        if stt.available():
            audio = st.file_uploader("강의 녹음 (m4a·mp3·wav)", type=["m4a", "mp3", "wav"], key="bt_audio",
                                     max_upload_size=config.MAX_AUDIO_MB)
        else:
            audio = None
            st.info("음성 인식 키가 없어 녹음 받아쓰기를 쓸 수 없어요. '대본 붙여넣기'를 써 주세요.")
    with tab_paste:
        pasted = st.text_area("받아쓴 대본 (붙여넣은 대본이 녹음보다 우선)", key="bt_paste", height=160,
                              placeholder="교수님 강의를 받아쓴 글을 붙여 넣어 주세요. 없어도 분석할 수 있어요.")
    st.caption("녹음·대본이 없어도 자료만으로 분석해요(녹음 신호만 0). 올린 파일과 결과는 서버 디스크에 저장하지 않아요.")
    if st.button("분석 시작", disabled=(up is None or not key_ok), key="bt_start", width="stretch"):
        audio_pair = None
        if audio is not None:
            try:
                stt.check_audio(audio.name, audio.size)
                audio_pair = (audio.name, audio.getvalue())
            except stt.STTError:
                show_error("E-04")
        if up.size > config.MAX_MATERIAL_MB * 1024 * 1024:
            show_error("E-02")
        else:
            src = "paste" if (pasted or "").strip() else None
            run_analysis(up.name, up.getvalue(), pasted, src, False, audio_pair)
    left = session_left(S["analyses_used"], config.MAX_ANALYSES_PER_SESSION)
    if 0 <= left <= 2:
        st.caption(f"이 화면에서 분석은 {left}번 더 할 수 있어요.")
