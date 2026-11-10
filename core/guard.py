"""F14 API 비용 보호. streamlit 의존 없음."""
from __future__ import annotations

import copy
import datetime as _dt
import threading
from collections import OrderedDict


def session_left(used: int, limit: int) -> int:
    """세션에서 남은 분석 횟수. limit이 0 이하면 제한 없음(-1). 음수로 내려가지 않는다."""
    if limit <= 0:
        return -1
    return max(0, limit - int(used or 0))


class DailyCounter:
    """서버 전체 하루 분석 횟수. 날짜가 바뀌면 0부터. 잠금으로 스레드 안전. limit 0은 제한 없음."""

    def __init__(self, limit: int, today=None):
        self.limit = int(limit)
        self._today = today or (lambda: _dt.date.today())
        self._lock = threading.Lock()
        self._day = self._today()
        self._count = 0

    def _roll(self):
        d = self._today()
        if d != self._day:
            self._day = d
            self._count = 0

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

    @property
    def count(self) -> int:
        with self._lock:
            self._roll()
            return self._count


class ResultCache:
    """샘플 진단 문제처럼 모두가 같은 결과를 쓰는 것을 서버 메모리에 둔다. 넘치면 오래된 것부터 버린다."""

    def __init__(self, max_items: int = 200):
        self.max_items = max_items
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            if key not in self._data:
                return None
            return copy.deepcopy(self._data[key])  # 꺼낼 때는 복사본

    def put(self, key, value) -> None:
        with self._lock:
            self._data[key] = copy.deepcopy(value)
            self._data.move_to_end(key)
            while len(self._data) > self.max_items:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def __contains__(self, key) -> bool:
        with self._lock:
            return key in self._data
