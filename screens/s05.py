"""S05 안내·설정: 사용 방법, 주의, 데이터 처리, 현재 설정, 이번 세션 사용량, 팀 정보."""
from __future__ import annotations

import streamlit as st

import config
from core import llm, stt
from screens import common as C


def render() -> None:
    C.header(5, "안내·설정", "사용 방법과 주의, 지금 설정과 이번 세션 사용량이에요.")
    st.markdown(
        "#### 사용 방법\n"
        "1. **자료 올리기**: 강의자료(PDF/PPTX)와 녹음 또는 대본을 올리고 분석을 시작해요(파일이 없으면 '샘플로 체험').\n"
        "2. **출제 포인트**: 출제 가능성 점수 순위와 근거(학습목표·본문 쪽수·예제·연습문제·교수님 말)를 봐요.\n"
        "3. **취약점 진단**: 출제 가능성 점수 20점 이상인 개념을 객관식·서술형으로 풀어 앎·헷갈림·모름을 가려요.\n"
        "4. **공부 순서**: 출제 점수 × 모르는 정도로 정한 순서, 오답노트와 보완 설명, 요약 노트를 보고 내려받아요."
    )
    st.markdown("#### 주의")
    st.markdown(
        f"- {C.DISCLAIMER}\n"
        "- 녹음은 교수님 허락을 받은 것만, 개인 학습 목적으로만 올려 주세요.\n"
        f"- {C.SEND_NOTICE}\n"
        f"- {C.STORE_NOTICE}\n"
        "- 학번·주민등록번호·전화번호·이메일은 AI에 보내기 전에 [마스킹]으로 가려요(강의자료와 대본 모두)."
    )
    usage = st.session_state["usage"]
    times = st.session_state["step_times"]
    rows = [
        ("언어 모델", config.LLM_MODEL),
        ("음성 인식", "사용 가능" if stt.available() else "키 없음 · 대본 붙여넣기만"),
        ("진단 기준", f"출제 가능성 점수 {config.DIAG_MIN_PCT}점 이상 전부 (빠른 진단은 상위 {config.QUICK_DIAG_TOP}개)"),
        ("문제 형식", st.session_state["q_mode"] + f" (섞어서: {config.ESSAY_MIN_PCT}점 이상 서술형)"),
        ("가중치 버전", config.WEIGHTS_VERSION),
        ("가짜 AI 모드", "켜짐" if llm.fake_mode() else "꺼짐"),
        ("이번 세션 AI 호출 수", f"{usage.calls}번"),
        ("입력 · 출력 토큰", f"{usage.input_tokens:,} · {usage.output_tokens:,}"),
        ("단계별 걸린 시간", " · ".join(f"{k} {v:.1f}초" for k, v in times.items()) or "-"),
        ("분석 횟수 (이 화면)", f"{st.session_state['analyses_used']} / {config.MAX_ANALYSES_PER_SESSION}"),
        ("오늘 서버 전체 분석 횟수", f"{C.daily_analyses().count} / {config.MAX_ANALYSES_PER_DAY}"),
        ("오늘 서버 전체 AI 호출 수", f"{C.daily_calls().count} / {config.MAX_AI_CALLS_PER_DAY}"),
    ]
    st.markdown("#### 현재 설정과 사용량")
    C.html_block("<table style='border-collapse:collapse;width:100%'>" + "".join(
        f"<tr><td style='padding:4px 10px;opacity:.8'>{C.esc(k)}</td><td style='padding:4px 10px'><b>{C.esc(v)}</b></td></tr>"
        for k, v in rows) + "</table>")
    st.caption("AI 호출 수는 호출마다 세요. 저장된 결과를 다시 쓰면 AI를 부르지 않으므로 더하지 않아요.")
    st.markdown("#### 정보")
    st.markdown(
        f"- 팀: {config.TEAM_NAME} · KOREATECH AI 실습형 이벤트 'Build for Students'\n"
        f"- 저장소: [{config.REPO_URL}]({config.REPO_URL})\n"
        "- 라이선스: MIT"
    )
