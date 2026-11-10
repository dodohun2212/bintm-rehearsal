# T-35~T-39 API 비용 보호, 빠른 진단 대상, 호출 수 세기
import datetime as dt
import threading

import config
from core.diagnose import diag_targets
from core.guard import DailyCounter, ResultCache, session_left
from core.llm import Usage


def test_t35_session_left():
    assert [session_left(u, 5) for u in (0, 4, 5, 9)] == [5, 1, 0, 0]
    assert session_left(3, 0) == -1
    assert config.MAX_ANALYSES_PER_SESSION > 0
    assert config.MAX_ANALYSES_PER_DAY >= config.MAX_ANALYSES_PER_SESSION
    assert config.QUICK_DIAG_TOP > 0


def test_t36_daily_counter():
    day = [dt.date(2026, 11, 11)]
    c = DailyCounter(3, today=lambda: day[0])
    assert [c.try_take() for _ in range(4)] == [True, True, True, False] and c.count == 3
    c.give_back()
    assert c.try_take()
    day[0] = dt.date(2026, 11, 12)
    assert c.count == 0 and c.try_take()
    free = DailyCounter(0)
    assert all(free.try_take() for _ in range(500))
    big = DailyCounter(100)
    ok = []

    def worker():
        for _ in range(50):
            if big.try_take():
                ok.append(1)

    ts = [threading.Thread(target=worker) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(ok) == 100


def test_t37_result_cache():
    rc = ResultCache(max_items=2)
    rc.put("a", {"v": 1})
    rc.put("b", {"v": 2})
    rc.put("c", {"v": 3})
    assert rc.get("a") is None and rc.get("b") == {"v": 2} and rc.get("c") == {"v": 3}
    got = rc.get("b")
    got["v"] = 99
    assert rc.get("b") == {"v": 2}  # 꺼낼 때는 복사본


def test_t38_quick_targets():
    pcts = [100, 95, 90, 80, 70, 60, 50, 40, 30, 20, 19, 10, 0]
    scores = [{"concept_id": f"c{i}", "pct": p} for i, p in enumerate(pcts)]
    assert len(diag_targets(scores)) == 10
    assert diag_targets(scores, top=None) == diag_targets(scores)
    assert diag_targets(scores, top=5) == ["c0", "c1", "c2", "c3", "c4"]
    assert len(diag_targets(scores, top=50)) == 10


def test_t39_usage_merge():
    batch = Usage()
    batch.add(100, 50)
    batch.add(110, 40)
    total = Usage()
    total.merge(batch)
    total.add(100, 35)
    assert total.calls == 3 and total.input_tokens == 310 and total.output_tokens == 125
