"""Derived views on the pre-expanded occurrence window (no HA imports).

Used by the sensors ("events today", "next event") and by the reminder
scheduler that fires ``timetree_reminder`` events.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import Any


def as_datetime(value: date | datetime, tz: tzinfo) -> datetime:
    """Aware datetime; all-day dates become local midnight."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=tz)
    return datetime.combine(value, time.min, tzinfo=tz)


def is_all_day(item: Any) -> bool:
    return not isinstance(item.dtstart, datetime)


def events_on(window: Iterable[Any], day: date, tz: tzinfo) -> list[Any]:
    """Occurrences overlapping the local calendar day ``day``."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    end = start + timedelta(days=1)
    return [
        item
        for item in window
        if as_datetime(item.dtstart, tz) < end and as_datetime(item.dtend, tz) > start
    ]


def next_event(window: Iterable[Any], now: datetime) -> Any | None:
    """First occurrence that has not started yet (window is sorted by start)."""
    for item in window:
        if as_datetime(item.dtstart, now.tzinfo) > now:
            return item
    return None


@dataclass(frozen=True, slots=True)
class Reminder:
    """A TimeTree alert that became due."""

    fire_at: datetime
    minutes_before: int
    item: Any

    @property
    def key(self) -> tuple[str, str, int]:
        """Identity used to fire every reminder exactly once."""
        return (str(self.item.uid), self.item.dtstart.isoformat(), self.minutes_before)


def due_reminders(
    window: Iterable[Any],
    alerts_of: Callable[[str], list[int]],
    after: datetime,
    until: datetime,
) -> list[Reminder]:
    """Reminders with ``after < fire_at <= until``, ordered by fire time."""
    tz = until.tzinfo
    result: list[Reminder] = []
    for item in window:
        if not item.uid:
            continue
        for minutes in alerts_of(item.uid):
            fire_at = as_datetime(item.dtstart, tz) - timedelta(minutes=minutes)
            if after < fire_at <= until:
                result.append(Reminder(fire_at, minutes, item))
    result.sort(key=lambda r: r.fire_at)
    return result


def describe(item: Any, tz: tzinfo, label: Any | None = None) -> dict[str, Any]:
    """Serializable summary of one occurrence (sensor attributes, event data)."""
    return {
        "uid": item.uid,
        "summary": item.summary or "",
        "start": as_datetime(item.dtstart, tz).isoformat(),
        "end": as_datetime(item.dtend, tz).isoformat(),
        "all_day": is_all_day(item),
        "location": item.location or None,
        "description": item.description or None,
        "label_id": getattr(label, "label_id", None),
        "label": getattr(label, "name", None),
    }
