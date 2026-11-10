"""T-35~T-39 API 비용 보호, 빠른 진단 대상, 호출 수 세기."""
import threading

import config
from core.diagnose import diag_targets
from core.guard import DailyCounter, ResultCache, session_left
from core.llm import Usage, run_parallel


def test_t35_session_left():
    assert [session_left(u, 5) for u in (0, 4, 5, 9)] == [5, 1, 0, 0]
    assert session_left(3, 0) == -1
    assert config.MAX_ANALYSES_PER_SESSION > 0
    assert config.MAX_ANALYSES_PER_DAY >= config.MAX_ANALYSES_PER_SESSION
    assert config.QUICK_DIAG_TOP > 0


def test_t36_daily_counter():
    day = ["2026-11-11"]
    c = DailyCounter(3, today=lambda: day[0])
    assert [c.try_take() for _ in range(4)] == [True, True, True, False]
    assert c.count == 3
    c.give_back()
    assert c.try_take() is True
    day[0] = "2026-11-12"
    assert c.count == 0
    unlimited = DailyCounter(0)
    assert all(unlimited.try_take() for _ in range(500))


def test_t36_thread_safe():
    c = DailyCounter(100)
    ok = []
    lock = threading.Lock()

    def worker():
        n = sum(1 for _ in range(50) if c.try_take())
        with lock:
            ok.append(n)

    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sum(ok) == 100


def test_t37_result_cache():
    rc = ResultCache(max_items=2)
    rc.put("a", {"v": 1})
    rc.put("b", {"v": 2})
    rc.put("c", {"v": 3})
    assert rc.get("a") is None
    assert rc.get("b") == {"v": 2} and rc.get("c") == {"v": 3}
    got = rc.get("b")
    got["v"] = 99
    assert rc.get("b") == {"v": 2}  # 꺼낼 때는 복사본


def test_t38_quick_targets():
    pcts = [100, 90, 80, 70, 60, 50, 40, 30, 25, 20, 19, 10, 0]
    scores = [{"concept_id": f"c{i}", "pct": p} for i, p in enumerate(pcts)]
    assert len(diag_targets(scores)) == 10
    assert diag_targets(scores, top=None) == diag_targets(scores)
    assert diag_targets(scores, top=5) == ["c0", "c1", "c2", "c3", "c4"]
    assert len(diag_targets(scores, top=50)) == 10


def test_t39_usage_merge():
    session = Usage()
    batch = Usage()
    batch.add(100, 50)
    batch.add(110, 25)
    session.merge(batch)
    session.add(100, 50)
    assert (session.calls, session.input_tokens, session.output_tokens) == (3, 310, 125)


def test_t39_parallel_counts_each_call():
    def job(u):
        u.add(10, 5)
        u.add(10, 5)
        return 1

    res, errs, usage = run_parallel({k: job for k in range(3)}, workers=3)
    assert len(res) == 3 and not errs
    assert usage.calls == 6


def test_t37_sample_questions_reused_in_app():
    """샘플 자료의 진단 문제는 두 번째 사람부터 AI를 부르지 않는다(빈 저장소도 재사용 대상)."""
    from streamlit.testing.v1 import AppTest

    from tests.helpers import ROOT

    calls = []
    for _ in range(2):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60).run()
        next(b for b in at.button if b.label == "샘플로 체험").click().run()
        before = at.session_state["usage"].calls
        next(b for b in at.button if "개념 진단하기" in b.label).click().run()
        assert not at.exception
        calls.append(at.session_state["usage"].calls - before)
    assert calls[0] > 0 and calls[1] == 0
