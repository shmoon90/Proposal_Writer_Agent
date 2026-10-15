"""영업일 계산 (결정적). 주말과 설정된 공휴일을 제외한다."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta


class BusinessCalendar:
    def __init__(
        self, holidays: Iterable[date] = (), *, workdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    ) -> None:
        self._holidays = frozenset(holidays)
        self._workdays = frozenset(workdays)

    def is_business_day(self, d: date) -> bool:
        return d.weekday() in self._workdays and d not in self._holidays

    def next_business_day(self, d: date) -> date:
        while not self.is_business_day(d):
            d += timedelta(days=1)
        return d

    def add_business_days(self, start: date, days: int) -> date:
        """``start``를 포함해 ``days`` 영업일째 날짜. days=1이면 start(영업일 보정)."""
        if days < 1:
            raise ValueError("days는 1 이상이어야 합니다.")
        d = self.next_business_day(start)
        remaining = days - 1
        while remaining > 0:
            d = self.next_business_day(d + timedelta(days=1))
            remaining -= 1
        return d

    def offset(self, start: date, days: int) -> date:
        """``start``에서 ``days`` 영업일 뒤(음수면 앞)의 날짜. 0이면 start 보정."""
        d = self.next_business_day(start)
        step = 1 if days >= 0 else -1
        remaining = abs(days)
        while remaining > 0:
            d += timedelta(days=step)
            while not self.is_business_day(d):
                d += timedelta(days=step)
            remaining -= 1
        return d

    def business_days_between(self, start: date, end: date) -> int:
        """start~end(포함) 영업일 수. end < start면 0."""
        if end < start:
            return 0
        count = 0
        d = start
        while d <= end:
            if self.is_business_day(d):
                count += 1
            d += timedelta(days=1)
        return count

    def business_days_by_month(self, start: date, end: date) -> dict[str, int]:
        out: dict[str, int] = {}
        d = start
        while d <= end:
            if self.is_business_day(d):
                key = f"{d.year:04d}-{d.month:02d}"
                out[key] = out.get(key, 0) + 1
            d += timedelta(days=1)
        return out


def parse_holidays(raw: str | Iterable[str]) -> list[date]:
    items = raw.split(",") if isinstance(raw, str) else list(raw)
    out: list[date] = []
    for item in items:
        s = item.strip()
        if s:
            out.append(date.fromisoformat(s))
    return out
