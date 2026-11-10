"""T-54: 화면 흐름 (AppTest, 가짜 AI). 샘플 체험 → 진단하기 → 답 없이 채점 → 예시 답 채우기 → 채점 → 공부 순서 → S05."""
from tests.apphelp import all_text, click, new_app, sample_to_s03


def test_t54_full_flow():
    at = new_app()
    assert not at.exception
    assert "출제를 보장하지 않습니다" in all_text(at)
    sample_to_s03(at)
    assert not at.exception, at.exception
    assert at.session_state["step"] == 3
    n = len(at.session_state["questions"])
    assert n == len(at.session_state["diag_ids"]) and n > 0

    # 답 없이 채점: 채점하지 않고 카드마다 미답 표시가 바로 보인다
    click(at, "채점하기")
    assert not at.exception
    assert at.session_state["grading"] == {}
    text = all_text(at)
    assert text.count("아직 답하지 않았어요") == n
    assert "아직 답하지 않은 문제: Q1" in text

    # 예시 답 채우기 → 채점
    click(at, "예시 답 채우기 (샘플 체험용)")
    assert "답한 문제 {0} / {0}".format(n) in at.get("progress")[0].proto.text
    click(at, "채점하기")
    assert not at.exception
    statuses = {g["status"] for g in at.session_state["grading"].values()}
    assert statuses == {"앎", "헷갈림", "모름"}

    click(at, "공부 순서 보기")
    assert not at.exception, at.exception
    assert at.session_state["step"] == 4
    assert [t.label for t in at.tabs] == ["🎯 공부 순서와 오답노트", "📒 시험 대비 요약 노트"]
    text = all_text(at)
    assert "내가 헷갈린 점에 대한 답" in text
    labels = [d.proto.label for d in at.get("download_button")]
    assert labels.count("📥 공부 순서·오답노트 내려받기") == 2 and labels.count("📒 요약 노트 내려받기") == 2
    assert len(at.session_state["notes"]) == len(at.session_state["concepts"])

    click(at, "⑤ 안내·설정")
    assert not at.exception
    assert at.session_state["usage"].calls > 0
    assert "이번 세션 AI 호출 수" in all_text(at)
