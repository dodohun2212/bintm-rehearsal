"""F14 API 비용 보호. streamlit에 의존하지 않는다(테스트 가능)."""
from __future__ import annotations

import copy
import datetime as _dt
import threading
from collections import OrderedDict


def session_left(used: int, limit: int) -> int:
    """남은 분석 횟수. limit이 0 이하면 제한 없음(-1)."""
    if limit <= 0:
        return -1
    return max(limit - used, 0)


class DailyCounter:
    """서버 전체 하루 분석 횟수. 날짜가 바뀌면 0부터. 잠금으로 스레드 안전."""

    def __init__(self, limit: int, today=None):
        self.limit = limit
        self._today = today or (lambda: _dt.date.today().isoformat())
        self._day = self._today()
        self._count = 0
        self._lock = threading.Lock()

    def _roll(self) -> None:
        d = self._today()
        if d != self._day:
            self._day = d
            self._count = 0

    @property
    def count(self) -> int:
        with self._lock:
            self._roll()
            return self._count

    def try_take(self) -> bool:
        with self._lock:
            self._roll()
            if self.limit > 0 and self._count >= self.limit:
                return False
            self._count += 1
            return True

    def give_back(self) -> None:
        with self._lock:
            self._roll()
            if self._count > 0:
                self._count -= 1


class ResultCache:
    """샘플 자료의 진단 문제 재사용. 넘치면 오래된 것부터 버린다. 꺼낼 때는 복사본."""

    def __init__(self, max_items: int = 200):
        self.max_items = max_items
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._data:
                return None
            return copy.deepcopy(self._data[key])

    def put(self, key, value) -> None:
        with self._lock:
            self._data[key] = copy.deepcopy(value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)
