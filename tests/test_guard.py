"""T-35~T-39 비용 보호와 호출 수 세기."""
import threading
from datetime import date

import config
from core.guard import DailyCounter, ResultCache, refund_needed, session_left


def test_t35_session_left():
    assert [session_left(u, 5) for u in (0, 4, 5, 9)] == [5, 1, 0, 0]
    assert session_left(3, 0) == -1
    assert config.MAX_ANALYSES_PER_SESSION > 0
    assert config.MAX_ANALYSES_PER_DAY >= config.MAX_ANALYSES_PER_SESSION
    assert config.QUICK_DIAG_TOP > 0


def test_t36_daily_counter():
    day = {"d": date(2026, 11, 11)}
    c = DailyCounter(3, today=lambda: day["d"])
    assert [c.try_take() for _ in range(4)] == [True, True, True, False]
    assert c.count == 3
    c.give_back()
    assert c.try_take() is True
    day["d"] = date(2026, 11, 12)
    assert c.count == 0
    unlimited = DailyCounter(0)
    assert all(unlimited.try_take() for _ in range(500))


def test_t36_daily_counter_threads():
    c = DailyCounter(100)
    ok = []
    lock = threading.Lock()

    def work():
        for _ in range(50):
            r = c.try_take()
            with lock:
                ok.append(r)

    ts = [threading.Thread(target=work) for _ in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert sum(ok) == 100 and c.count == 100


def test_t37_result_cache_evicts_oldest():
    rc = ResultCache(max_items=2)
    rc.put("a", {"v": 1})
    rc.put("b", {"v": 2})
    rc.put("c", {"v": 3})
    assert rc.get("a") is None and rc.get("b") == {"v": 2} and rc.get("c") == {"v": 3}
    got = rc.get("b")
    got["v"] = 99
    assert rc.get("b") == {"v": 2}  # 꺼낸 것은 복사본
    empty = ResultCache()
    assert len(empty) == 0
    assert empty is not None  # 비어 있으면 거짓이므로 'is not None'으로 검사해야 한다


def test_t59_refund_rules():
    assert refund_needed(failed=True, ai_calls=0) == (True, True)
    assert refund_needed(failed=False, ai_calls=0) == (False, True)
    assert refund_needed(failed=True, ai_calls=1) == (False, False)
    assert refund_needed(failed=False, ai_calls=2) == (False, False)
