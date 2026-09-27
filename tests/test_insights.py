"""Today / next event / reminder scheduling on the occurrence window (1.5.0)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from custom_components.timetree.insights import (
    describe,
    due_reminders,
    events_on,
    next_event,
)
from custom_components.timetree.store import EventStore

TZ = ZoneInfo("Europe/Berlin")


@dataclass
class Occ:
    uid: str
    dtstart: date | datetime
    dtend: date | datetime
    summary: str = "x"
    location: str | None = None
    description: str | None = None


NOW = datetime(2026, 10, 3, 12, 0, tzinfo=TZ)
WINDOW = [
    Occ("allday", date(2026, 10, 3), date(2026, 10, 4), "Holiday"),
    Occ("morning", NOW - timedelta(hours=3), NOW - timedelta(hours=2), "Breakfast"),
    Occ("evening", NOW + timedelta(hours=6), NOW + timedelta(hours=7), "Dinner", "Cafe"),
    Occ("overnight", NOW + timedelta(hours=11), NOW + timedelta(hours=13), "Night shift"),
    Occ("tomorrow", date(2026, 10, 4), date(2026, 10, 5), "Trip"),
]


def test_events_on_day_includes_all_day_past_and_overnight():
    assert [o.uid for o in events_on(WINDOW, NOW.date(), TZ)] == [
        "allday", "morning", "evening", "overnight",
    ]
    assert [o.uid for o in events_on(WINDOW, date(2026, 10, 4), TZ)] == ["overnight", "tomorrow"]


def test_next_event_skips_running_and_all_day_of_today():
    assert next_event(WINDOW, NOW).uid == "evening"
    assert next_event(WINDOW, NOW + timedelta(days=5)) is None


def test_due_reminders_fire_in_window_only():
    alerts = {"evening": [15, 360], "tomorrow": [60]}.get
    got = due_reminders(WINDOW, lambda uid: alerts(uid) or [], NOW - timedelta(minutes=1), NOW)
    assert [(r.item.uid, r.minutes_before) for r in got] == [("evening", 360)]

    later = NOW + timedelta(hours=5, minutes=45)
    got = due_reminders(WINDOW, lambda uid: alerts(uid) or [], later - timedelta(minutes=1), later)
    assert [(r.item.uid, r.minutes_before) for r in got] == [("evening", 15)]


def test_all_day_reminder_is_relative_to_local_midnight():
    alerts = {"tomorrow": [60]}.get
    fire = datetime(2026, 10, 3, 23, 0, tzinfo=TZ)
    got = due_reminders(WINDOW, lambda uid: alerts(uid) or [], fire - timedelta(minutes=1), fire)
    assert [r.item.uid for r in got] == ["tomorrow"]
    assert got[0].key == ("tomorrow", "2026-10-04", 60)


def test_describe_is_json_friendly():
    d = describe(WINDOW[2], TZ)
    assert d["summary"] == "Dinner" and d["location"] == "Cafe" and d["all_day"] is False
    assert d["start"].startswith("2026-10-03T18:00") and d["label"] is None


def test_store_alerts_are_sanitised():
    store = EventStore()
    store.merge(
        [
            {"uuid": "a", "alerts": [15, 60, 15, True, "5", 10**9, -540]},
            {"uuid": "b", "alerts": None},
            {"uuid": "c"},
        ],
        1,
    )
    assert store.alerts_of("a") == [15, 60, -540]
    assert store.alerts_of("b") == [] and store.alerts_of("c") == [] and store.alerts_of("zz") == []
