"""F14 API 비용 보호. streamlit에 기대지 않는다(테스트 가능)."""
from __future__ import annotations

import copy
import threading
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def kst_now() -> datetime:
    """한국 시간. 배포 서버는 UTC라 그대로 쓰면 오전 9시 전에 전날이 된다."""
    return datetime.now(KST)


def kst_today() -> date:
    return datetime.now(KST).date()


def session_left(used: int, limit: int) -> int:
    """남은 분석 횟수. limit이 0 이하면 제한 없음(-1)."""
    if limit <= 0:
        return -1
    return max(0, limit - max(0, used))


def refund_needed(failed: bool, ai_calls: int) -> tuple[bool, bool]:
    """분석 횟수를 돌려줄지 (세션, 하루).

    - AI를 부르기 전에 실패(스캔 PDF 등): 둘 다 돌려준다.
    - 저장된 결과만으로 끝남(AI 호출 0번): 하루 횟수만 돌려준다.
    - AI를 한 번이라도 불렀으면: 돌려주지 않는다.
    """
    if ai_calls > 0:
        return (False, False)
    if failed:
        return (True, True)
    return (False, True)


class DailyCounter:
    """서버 전체 하루 횟수. 날짜가 바뀌면 0부터. 잠금으로 스레드 안전. limit 0은 제한 없음."""

    def __init__(self, limit: int, today=kst_today):
        self.limit = int(limit)
        self._today = today
        self._day = today()
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

    def try_take(self, n: int = 1) -> bool:
        with self._lock:
            self._roll()
            if self.limit > 0 and self._count + n > self.limit:
                return False
            self._count += n
            return True

    def add(self, n: int) -> None:
        """실제로 쓴 만큼 더한다(AI 호출 수)."""
        with self._lock:
            self._roll()
            self._count += max(0, int(n))

    def exhausted(self) -> bool:
        with self._lock:
            self._roll()
            return self.limit > 0 and self._count >= self.limit

    def give_back(self, n: int = 1) -> None:
        with self._lock:
            self._roll()
            self._count = max(0, self._count - n)


class ResultCache:
    """서버 공용 결과 저장소(샘플 문제·설명·노트 재사용). 넘치면 오래된 것부터 버린다."""

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

    def __contains__(self, key) -> bool:
        with self._lock:
            return key in self._data

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
