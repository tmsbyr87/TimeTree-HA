"""Tests for the incremental-sync EventStore (R5, R8)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from custom_components.timetree.store import EventStore

BERLIN = ZoneInfo("Europe/Berlin")


def _raw(uid: str, title: str = "x", deleted: bool = False):
    start = int(datetime(2026, 10, 3, 9, 0, tzinfo=BERLIN).timestamp() * 1000)
    return {
        "uuid": uid,
        "title": title,
        "all_day": False,
        "start_at": start,
        "end_at": start + 3_600_000,
        "start_timezone": "Europe/Berlin",
        "end_timezone": "Europe/Berlin",
        "type": 0,
        "category": 1,
        "recurrences": None,
        "deactivated_at": 1 if deleted else None,
    }


def test_initial_merge_and_cursor():
    store = EventStore()
    assert store.cursor is None
    store.merge([_raw("a"), _raw("b")], cursor=100)
    assert store.count == 2
    assert store.cursor == 100
    assert {e.uid for e in store.calendar().events} == {"a", "b"}


def test_incremental_update_replaces_by_uuid():
    store = EventStore()
    store.merge([_raw("a", "alt")], cursor=1)
    store.merge([_raw("a", "neu")], cursor=2)
    assert store.count == 1
    assert store.calendar().events[0].summary == "neu"
    assert store.cursor == 2


def test_deleted_event_is_removed():
    store = EventStore()
    store.merge([_raw("a"), _raw("b")], cursor=1)
    store.merge([_raw("a", deleted=True)], cursor=2)
    assert store.count == 1
    assert [e.uid for e in store.calendar().events] == ["b"]


def test_calendar_is_cached_until_next_merge():
    store = EventStore()
    store.merge([_raw("a")], cursor=1)
    first = store.calendar()
    assert store.calendar() is first
    store.merge([], cursor=2)
    assert store.calendar() is not first


def test_timeline_is_cached_per_timezone_and_invalidated_on_merge():
    store = EventStore()
    store.merge([_raw("a")], cursor=1)
    t1 = store.timeline(BERLIN)
    assert store.timeline(BERLIN) is t1
    assert store.timeline(ZoneInfo("UTC")) is not t1
    # a merge must drop the cache so new events show up
    store.merge([_raw("b")], cursor=2)
    t2 = store.timeline(BERLIN)
    assert t2 is not t1
    starts = [i.uid for i in t2.overlapping(
        datetime(2026, 10, 1, tzinfo=BERLIN), datetime(2026, 10, 5, tzinfo=BERLIN)
    )]
    assert sorted(starts) == ["a", "b"]


def test_build_window_materialises_sorted_occurrences_and_is_cleared_on_reset():
    store = EventStore()
    weekly = _raw("w", "Wöchentlich")
    weekly["recurrences"] = ["RRULE:FREQ=WEEKLY;COUNT=5"]
    store.merge([_raw("a", "Einzeln"), weekly], cursor=1)

    start = datetime(2026, 10, 1, tzinfo=BERLIN)
    end = datetime(2026, 10, 20, tzinfo=BERLIN)
    window = store.build_window(BERLIN, start, end)

    assert window is store.window
    # 3.10. (a + w), 10.10. (w), 17.10. (w) → 4 occurrences, sorted by start
    assert [i.uid for i in window] == ["a", "w", "w", "w"]
    starts = [i.dtstart for i in window]
    assert starts == sorted(starts)

    store.reset()
    assert store.window == []


def test_labels_are_resolved_per_event_uid():
    from custom_components.timetree.api import TimeTreeLabel

    store = EventStore()
    a = _raw("a"); a["label_id"] = 3
    b = _raw("b")  # no label
    store.merge([a, b], cursor=1)
    store.set_labels({3: TimeTreeLabel(3, "WICHTIG", "#c0392b")})
    assert store.label_id_of("a") == 3
    assert store.label_of("a").name == "WICHTIG"
    assert store.label_id_of("b") is None and store.label_of("b") is None
    assert store.label_of("unknown") is None


def test_reset_clears_everything():
    store = EventStore()
    store.merge([_raw("a")], cursor=5)
    store.reset()
    assert store.count == 0
    assert store.cursor is None
    assert store.calendar().events == []


def test_one_malformed_event_does_not_break_the_calendar():
    """Regression for the live crash: a bad event must be skipped, not fatal."""
    store = EventStore()
    bad = _raw("bad")
    bad["end_at"] = "not-a-number"  # forces a TypeError inside conversion
    store.merge([_raw("good"), bad], cursor=1)
    cal = store.calendar()  # must not raise
    assert [e.uid for e in cal.events] == ["good"]


def test_events_without_uuid_are_ignored():
    store = EventStore()
    raw = _raw("a")
    raw.pop("uuid")
    store.merge([raw], cursor=1)
    assert store.count == 0
