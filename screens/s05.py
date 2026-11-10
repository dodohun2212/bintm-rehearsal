"""S05 안내·설정: 사용 방법, 주의, 현재 설정, 이번 세션 사용량."""
from __future__ import annotations

import streamlit as st

import config
from core import stt
from core.html import DISCLAIMER, esc
from core.score import WEIGHTS_VERSION
from screens.common import S, counters, html, usage


def render() -> None:
    st.title("⑤ 안내·설정")
    st.subheader("사용 방법")
    st.markdown("1. **① 자료 올리기**: 강의자료(PDF·PPTX)와 녹음 또는 대본을 올리거나 '샘플 자료로 체험하기'를 눌러요.\n"
                "2. **② 출제 포인트**: 출제 가능성 점수 순위와 근거(학습목표·본문 쪽수·예제·연습문제·교수님 말)를 봐요.\n"
                "3. **③ 취약점 진단**: 출제 점수 20점 이상 개념의 문제를 풀고 채점해요. 찍어서 맞힌 것은 '헷갈림'이에요.\n"
                "4. **④ 공부 순서**: 출제 점수 × 모르는 정도로 정한 순서, 오답노트, 시험 대비 요약 노트를 보고 내려받아요.")
    st.subheader("주의")
    html(f'<div class="bt-warn">⚠️ {esc(DISCLAIMER)}</div>')
    st.markdown("- 녹음은 교수님 허락을 받고 개인 학습 목적으로만 써 주세요.\n"
                "- 올린 파일과 결과는 서버 디스크에 저장하지 않아요. 결과는 이 브라우저 탭(세션)에만 있고, "
                "같은 파일의 개념·강조 분석 결과와 쪽 그림만 서버 메모리 캐시에 잠시 둬요. 새로고침하면 결과가 사라지니 ④에서 내려받아 두세요.\n"
                "- 학번·주민등록번호·전화번호·이메일은 AI에 보내기 전에 [마스킹]으로 가려요.")
    st.subheader("현재 설정")
    rows = [("언어 모델", config.LLM_MODEL),
            ("음성 인식", f"{config.STT_MODEL} · {'사용 가능' if stt.available() else '키 없음(대본 붙여넣기만)'}"),
            ("진단 기준", f"출제 가능성 점수 {config.DIAG_MIN_PCT}점 이상 전부"),
            ("문제 형식", S["q_mode"]), ("가중치 버전", WEIGHTS_VERSION),
            ("사용 제한", f"세션당 분석 {config.MAX_ANALYSES_PER_SESSION}번 · 하루 분석 {config.MAX_ANALYSES_PER_DAY}번 · "
                       f"하루 AI 호출 {config.MAX_AI_CALLS_PER_DAY}번"),
            ("서버 전체 오늘 사용", f"분석 {counters()['analyses'].count}번 · AI 호출 {counters()['ai_calls'].count}번")]
    html("<table class='bt-tbl'>" + "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in rows)
         + "</table>")
    st.subheader("이번 세션 사용량")
    u = usage()
    rows2 = [("AI 호출 수", f"{u.calls}번"), ("입력 토큰", f"{u.input_tokens:,}"), ("출력 토큰", f"{u.output_tokens:,}"),
             ("AI 호출 시간 합", f"{u.seconds:.1f}초"), ("이 세션 분석 횟수", f"{S['analyses_used']}번")]
    rows2 += [(f"단계 · {k}", f"{v:.1f}초") for k, v in u.stages.items()]
    html("<table class='bt-tbl'>" + "".join(f"<tr><th>{esc(k)}</th><td>{esc(v)}</td></tr>" for k, v in rows2)
         + "</table>")
    st.caption("AI 호출 수는 호출마다 세요. 저장된 결과(샘플 문제·설명·노트, 같은 파일 분석)를 다시 쓰면 더하지 않아요. "
               "단계별 시간은 같은 단계를 여러 번 하면 더해요.")
    st.subheader("정보")
    st.markdown(f"- 팀: {config.TEAM_NAME}\n- 대회: {config.CONTEST_NAME}\n- 저장소: {config.REPO_URL}")
