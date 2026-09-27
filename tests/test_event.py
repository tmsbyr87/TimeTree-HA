"""Tests for TimeTree → ical event conversion (R6, R7, R9)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from ical.calendar import Calendar

from custom_components.timetree.event import (
    is_calendar_relevant,
    is_deleted,
    to_ical_event,
)

BERLIN = ZoneInfo("Europe/Berlin")


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _timed(**over):
    base = {
        "uuid": "ev-1",
        "title": "Zahnarzt",
        "note": "Mitbringen: Karte",
        "location": "Leipzig",
        "all_day": False,
        "start_at": _ms(datetime(2026, 10, 3, 9, 0, tzinfo=BERLIN)),
        "end_at": _ms(datetime(2026, 10, 3, 10, 0, tzinfo=BERLIN)),
        "start_timezone": "Europe/Berlin",
        "end_timezone": "Europe/Berlin",
        "type": 0,
        "category": 1,
        "recurrences": None,
        "deactivated_at": None,
    }
    base.update(over)
    return base


def test_timed_event_keeps_timezone_and_fields():
    ev = to_ical_event(_timed())
    assert ev is not None
    assert ev.uid == "ev-1"
    assert ev.summary == "Zahnarzt"
    assert ev.description == "Mitbringen: Karte"
    assert ev.location == "Leipzig"
    assert isinstance(ev.dtstart, datetime)
    assert ev.dtstart == datetime(2026, 10, 3, 9, 0, tzinfo=BERLIN)
    assert ev.dtend == datetime(2026, 10, 3, 10, 0, tzinfo=BERLIN)


def test_all_day_uses_dates_and_exclusive_end():
    # TimeTree: all-day 3.–4. Oktober, end_at points at start of the 4th (inclusive).
    raw = _timed(
        all_day=True,
        start_at=_ms(datetime(2026, 10, 3, 0, 0, tzinfo=BERLIN)),
        end_at=_ms(datetime(2026, 10, 4, 0, 0, tzinfo=BERLIN)),
    )
    ev = to_ical_event(raw)
    assert ev is not None
    assert ev.dtstart == date(2026, 10, 3)
    assert ev.dtend == date(2026, 10, 5)  # exclusive → +1 day


def test_single_all_day_event_spans_one_day():
    raw = _timed(
        all_day=True,
        start_at=_ms(datetime(2026, 10, 3, 0, 0, tzinfo=BERLIN)),
        end_at=_ms(datetime(2026, 10, 3, 0, 0, tzinfo=BERLIN)),
    )
    ev = to_ical_event(raw)
    assert ev.dtstart == date(2026, 10, 3)
    assert ev.dtend == date(2026, 10, 4)


def test_memo_and_birthday_are_skipped():
    assert not is_calendar_relevant(_timed(category=2))
    assert not is_calendar_relevant(_timed(type=1))
    assert to_ical_event(_timed(category=2)) is None
    assert to_ical_event(_timed(type=1)) is None


def test_deleted_detection():
    assert not is_deleted(_timed())
    assert is_deleted(_timed(deactivated_at=1700000000000))


def test_missing_uid_or_times_returns_none():
    assert to_ical_event(_timed(uuid=None)) is None
    assert to_ical_event(_timed(start_at=None)) is None


def test_empty_title_gets_placeholder():
    ev = to_ical_event(_timed(title="   "))
    assert ev.summary == "(ohne Titel)"


def test_weekly_rrule_expands_and_exdate_removes_instance():
    raw = _timed(
        recurrences=[
            "RRULE:FREQ=WEEKLY;BYDAY=SA;COUNT=4",
            # skip the second occurrence (10. Oktober 09:00 Berlin = 07:00Z)
            "EXDATE:20261010T070000Z",
        ]
    )
    ev = to_ical_event(raw)
    assert ev is not None
    assert ev.rrule is not None

    cal = Calendar()
    cal.events.append(ev)
    window_start = datetime(2026, 10, 1, tzinfo=BERLIN)
    window_end = datetime(2026, 11, 1, tzinfo=BERLIN)
    starts = [i.dtstart for i in cal.timeline_tz(BERLIN).overlapping(window_start, window_end)]

    assert datetime(2026, 10, 3, 9, 0, tzinfo=BERLIN) in starts
    assert datetime(2026, 10, 17, 9, 0, tzinfo=BERLIN) in starts
    assert datetime(2026, 10, 24, 9, 0, tzinfo=BERLIN) in starts
    assert datetime(2026, 10, 10, 9, 0, tzinfo=BERLIN) not in starts
    assert len(starts) == 3


def test_all_day_exdate_is_converted_to_date():
    raw = _timed(
        all_day=True,
        start_at=_ms(datetime(2026, 10, 3, 0, 0, tzinfo=BERLIN)),
        end_at=_ms(datetime(2026, 10, 3, 0, 0, tzinfo=BERLIN)),
        recurrences=["RRULE:FREQ=DAILY;COUNT=3", "EXDATE:20261004"],
    )
    ev = to_ical_event(raw)
    cal = Calendar()
    cal.events.append(ev)
    days = sorted(
        i.dtstart
        for i in cal.timeline.overlapping(date(2026, 10, 1), date(2026, 10, 10))
    )
    assert days == [date(2026, 10, 3), date(2026, 10, 5)]


def test_timed_event_with_date_until_is_aligned_and_expands():
    # Live bug: TimeTree sends UNTIL as a bare date on timed events; ical rejects
    # the DTSTART/UNTIL type mismatch unless we align it.
    raw = _timed(recurrences=["RRULE:FREQ=WEEKLY;BYDAY=SA;UNTIL=20261017"])
    ev = to_ical_event(raw)
    assert ev is not None, "event must not be dropped"
    assert isinstance(ev.rrule.until, datetime)
    assert ev.rrule.until.tzinfo is not None

    cal = Calendar()
    cal.events.append(ev)
    starts = [
        i.dtstart
        for i in cal.timeline_tz(BERLIN).overlapping(
            datetime(2026, 10, 1, tzinfo=BERLIN), datetime(2026, 12, 1, tzinfo=BERLIN)
        )
    ]
    # 3., 10., 17. Oktober – the 17th is still inside UNTIL (end of that day)
    assert starts == [
        datetime(2026, 10, 3, 9, 0, tzinfo=BERLIN),
        datetime(2026, 10, 10, 9, 0, tzinfo=BERLIN),
        datetime(2026, 10, 17, 9, 0, tzinfo=BERLIN),
    ]


def test_all_day_event_with_datetime_until_is_aligned():
    raw = _timed(
        all_day=True,
        start_at=_ms(datetime(2026, 10, 3, 0, 0, tzinfo=BERLIN)),
        end_at=_ms(datetime(2026, 10, 3, 0, 0, tzinfo=BERLIN)),
        recurrences=["RRULE:FREQ=DAILY;UNTIL=20261005T215959Z"],
    )
    ev = to_ical_event(raw)
    assert ev is not None
    assert ev.rrule.until == date(2026, 10, 5)
    cal = Calendar()
    cal.events.append(ev)
    days = [i.dtstart for i in cal.timeline.overlapping(date(2026, 10, 1), date(2026, 10, 10))]
    assert days == [date(2026, 10, 3), date(2026, 10, 4), date(2026, 10, 5)]


def test_invalid_rrule_is_ignored_not_fatal():
    ev = to_ical_event(_timed(recurrences=["RRULE:FREQ=BOGUS"]))
    assert ev is not None
    assert ev.rrule is None


def test_unknown_timezone_falls_back_to_utc():
    raw = _timed(start_timezone="Mars/Olympus", end_timezone="Mars/Olympus")
    ev = to_ical_event(raw)
    assert ev.dtstart.tzinfo is not None
    assert ev.dtstart.utcoffset() == timezone.utc.utcoffset(None)
