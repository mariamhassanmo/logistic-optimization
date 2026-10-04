"""Truck schedule logic: "when does the next truck leave, and how long do we wait?"

Assumptions (also in the README):
  * A schedule is a set of DAILY recurring times of day in Africa/Cairo. The same
    times apply every day; list order does not matter, so ["23:30", "01:00", "06:00"]
    simply means trucks leave at 01:00, 06:00 and 23:30 every day.
  * A truck departing exactly at `now` is still catchable (waiting = 0).
    Anything strictly earlier than `now` (even by one second) has already left.
  * Waiting time is REAL elapsed time (computed in UTC), so a DST change between
    now and the departure does not skew it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Iterable

from config import TIMEZONE

_UTC = timezone.utc


@dataclass(frozen=True)
class NextDeparture:
    departure: datetime  # timezone-aware, in the schedule timezone
    waiting: timedelta   # real elapsed time from `now` until departure

    @property
    def waiting_hours(self) -> float:
        return self.waiting.total_seconds() / 3600


def next_departure(
    schedule: Iterable[time], now: datetime, tz: tzinfo = TIMEZONE
) -> NextDeparture | None:
    """Return the next truck at or after `now`, or None if the schedule is empty.

    `now` must be timezone-aware (naive datetimes are rejected on purpose, since
    they are the classic source of midnight/day-boundary bugs).
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("`now` must be a timezone-aware datetime")

    times = list(schedule)
    if not times:
        return None

    now_utc = now.astimezone(_UTC)
    today = now.astimezone(tz).date()

    best: datetime | None = None
    # Today's and tomorrow's occurrences are enough: tomorrow's earliest truck
    # is always in the future, so a non-empty schedule always yields a result.
    for offset in (0, 1):
        day = today + timedelta(days=offset)
        for t in times:
            departure_utc = datetime.combine(day, t, tzinfo=tz).astimezone(_UTC)
            if departure_utc >= now_utc and (best is None or departure_utc < best):
                best = departure_utc

    assert best is not None  # unreachable for a non-empty schedule
    return NextDeparture(departure=best.astimezone(tz), waiting=best - now_utc)
