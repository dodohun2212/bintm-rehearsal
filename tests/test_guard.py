"""T-35~T-39: 세션·하루 분석 횟수, 결과 재사용, 빠른 진단 대상, 호출 수 세기."""
import threading
from datetime import date

import config
from core.guard import DailyCounter, ResultCache, session_left
from core.llm import Usage


def test_t35_session_left():
    assert [session_left(u, 5) for u in (0, 4, 5, 9)] == [5, 1, 0, 0]
    assert session_left(3, 0) == -1


def test_t35_config_values():
    assert config.MAX_ANALYSES_PER_SESSION > 0
    assert config.MAX_ANALYSES_PER_DAY >= config.MAX_ANALYSES_PER_SESSION
    assert config.QUICK_DIAG_TOP > 0


def test_t36_daily_counter_limit_and_give_back():
    c = DailyCounter(3)
    assert [c.try_take() for _ in range(4)] == [True, True, True, False]
    assert c.count == 3
    c.give_back()
    assert c.try_take() is True


def test_t36_daily_counter_new_day():
    days = [date(2026, 11, 10)]
    c = DailyCounter(2, today=lambda: days[0])
    c.try_take()
    c.try_take()
    assert c.try_take() is False
    days[0] = date(2026, 11, 11)
    assert c.count == 0
    assert c.try_take() is True


def test_t36_daily_counter_unlimited():
    c = DailyCounter(0)
    assert all(c.try_take() for _ in range(500))


def test_t36_daily_counter_thread_safe():
    c = DailyCounter(100)
    allowed = []
    lock = threading.Lock()

    def worker():
        for _ in range(50):
            ok = c.try_take()
            with lock:
                allowed.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(allowed) == 100


def test_t37_result_cache_drops_oldest():
    cache = ResultCache(max_items=2)
    cache.put("a", {"v": 1})
    cache.put("b", {"v": 2})
    cache.put("c", {"v": 3})
    assert cache.get("a") is None
    assert cache.get("b") == {"v": 2} and cache.get("c") == {"v": 3}


def test_t37_empty_cache_is_not_none():
    cache = ResultCache()
    assert len(cache) == 0 and cache is not None  # 비어 있으면 거짓이므로 `is not None`으로 검사해야 한다
    got = cache.get("x")
    got_copy_check = cache.put("k", {"a": [1]})
    item = cache.get("k")
    item["a"].append(2)
    assert cache.get("k") == {"a": [1]}  # 꺼낸 것은 복사본
    assert got is None and got_copy_check is None


def test_t39_usage_merge_counts_each_call():
    session = Usage()
    batch = Usage()
    batch.add(100, 50)
    batch.add(110, 40)
    session.merge(batch)
    session.add(100, 35)
    assert session.calls == 3
    assert session.input_tokens == 310 and session.output_tokens == 125
