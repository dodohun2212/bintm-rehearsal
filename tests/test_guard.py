"""T-35~T-39: 세션·하루 분석 횟수, 결과 재사용(클래스와 화면), 빠른 진단 대상, 호출 수 세기."""
import datetime as dt
import threading
from pathlib import Path

import config
from core.diagnose import diag_targets
from core.guard import DailyCounter, ResultCache, session_left
from core.llm import Usage

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_t35_session_left_and_config():
    assert [session_left(u, 5) for u in (0, 4, 5, 9)] == [5, 1, 0, 0]
    assert session_left(3, 0) == -1
    assert config.MAX_ANALYSES_PER_SESSION > 0
    assert config.MAX_ANALYSES_PER_DAY >= config.MAX_ANALYSES_PER_SESSION
    assert config.QUICK_DIAG_TOP > 0


def test_t36_daily_counter():
    day = [dt.date(2026, 11, 11)]
    c = DailyCounter(3, today=lambda: day[0])
    assert [c.try_take() for _ in range(4)] == [True, True, True, False]
    assert c.count == 3
    c.give_back()
    assert c.try_take() is True
    day[0] = dt.date(2026, 11, 12)
    assert c.count == 0 and c.try_take() is True
    free = DailyCounter(0)
    assert all(free.try_take() for _ in range(500))
    many = DailyCounter(100)
    ok = []

    def worker():
        for _ in range(50):
            if many.try_take():
                ok.append(1)
    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(ok) == 100 and many.count == 100


def test_t37_result_cache():
    rc = ResultCache(max_items=2)
    assert len(rc) == 0 and rc is not None  # 빈 저장소는 거짓이므로 'is not None'으로 검사해야 한다
    rc.put("a", {"v": 1})
    rc.put("b", {"v": 2})
    rc.put("c", {"v": 3})
    assert rc.get("a") is None and rc.get("b") == {"v": 2} and rc.get("c") == {"v": 3}
    got = rc.get("b")
    got["v"] = 99
    assert rc.get("b") == {"v": 2}  # 꺼낼 때는 복사본


def _sample_to_s03(at):
    at.run()
    next(b for b in at.button if "샘플" in b.label).click().run()
    next(b for b in at.button if "진단하기" in b.label).click().run()
    return at


def test_t37_second_session_reuses_sample_questions():
    """두 세션이 샘플 진단을 하면 두 번째는 문제 만들기 AI 호출이 0이다(화면 시험, 가짜 AI)."""
    from streamlit.testing.v1 import AppTest
    a = _sample_to_s03(AppTest.from_file(APP, default_timeout=60))
    assert not a.exception
    calls_after_analysis_a = a.session_state.usage.calls
    n_q = len(a.session_state.questions)
    assert n_q > 0
    b = AppTest.from_file(APP, default_timeout=60)
    b.run()
    next(x for x in b.button if "샘플" in x.label).click().run()
    calls_b_analysis = b.session_state.usage.calls
    next(x for x in b.button if "진단하기" in x.label).click().run()
    assert not b.exception
    assert len(b.session_state.questions) == n_q
    assert b.session_state.usage.calls == calls_b_analysis  # 문제 만들기에서 AI 호출 0
    assert calls_after_analysis_a >= n_q


def test_t38_quick_targets():
    pcts = [100, 90, 80, 70, 60, 50, 40, 30, 25, 20, 19, 10, 0]
    scores = [{"concept_id": f"c{i}", "pct": p} for i, p in enumerate(pcts)]
    full = diag_targets(scores)
    assert len(full) == 10
    assert diag_targets(scores, top=None) == full
    assert diag_targets(scores, top=5) == ["c0", "c1", "c2", "c3", "c4"]
    assert diag_targets(scores, top=50) == full


def test_t39_usage_merge_counts_calls():
    session = Usage()
    batch = Usage()
    batch.add(100, 50, 1.0)
    batch.add(110, 25, 1.0)
    session.merge(batch)
    session.add(100, 50, 1.0)
    assert (session.calls, session.input_tokens, session.output_tokens) == (3, 310, 125)
