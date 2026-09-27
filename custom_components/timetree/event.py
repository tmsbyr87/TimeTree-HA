"""Convert TimeTree event payloads into ``ical`` events.

No Home Assistant imports here so the conversion stays unit-testable.

TimeTree specifics (from the reference exporter):
* ``start_at``/``end_at`` are epoch milliseconds.
* ``all_day`` events carry an *inclusive* end; iCalendar wants an exclusive
  end, so one day is added.
* ``recurrences`` is a list of raw content lines such as
  ``"RRULE:FREQ=WEEKLY;BYDAY=MO"`` or ``"EXDATE:20260101T000000Z"``.
* Modified occurrences of a series arrive as separate events with
  ``recurring_uuid`` set; the parent carries a matching ``EXDATE``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ical.event import Event
from ical.types.recur import Recur

from .const import EVENT_CATEGORY_MEMO, EVENT_TYPE_BIRTHDAY

_LOGGER = logging.getLogger(__name__)

_UTC = timezone.utc


def is_deleted(raw: dict[str, Any]) -> bool:
    """Return True when the sync feed marks the event as removed."""
    return raw.get("deactivated_at") is not None


def is_calendar_relevant(raw: dict[str, Any]) -> bool:
    """Filter out memos and birthdays, matching the reference exporter."""
    if raw.get("category") == EVENT_CATEGORY_MEMO:
        return False
    if raw.get("type") == EVENT_TYPE_BIRTHDAY:
        return False
    return True


def _zone(name: str | None) -> ZoneInfo:
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        _LOGGER.debug("Unknown timezone %r, falling back to UTC", name)
        return ZoneInfo("UTC")


def _ms_to_datetime(ms: int | float, tz: ZoneInfo) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=_UTC).astimezone(tz)


def _parse_exdates(value: str) -> list[datetime | date]:
    """Parse the value part of an EXDATE line into dates/datetimes."""
    result: list[datetime | date] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            if len(token) == 8:
                result.append(datetime.strptime(token, "%Y%m%d").date())
            elif token.endswith("Z"):
                result.append(
                    datetime.strptime(token, "%Y%m%dT%H%M%SZ").replace(tzinfo=_UTC)
                )
            else:
                result.append(datetime.strptime(token, "%Y%m%dT%H%M%S"))
        except ValueError:
            _LOGGER.debug("Skipping unparsable EXDATE token %r", token)
    return result


def _split_content_line(line: str) -> tuple[str, str]:
    """Split ``NAME;PARAM=X:VALUE`` into (name, value)."""
    head, _, value = line.partition(":")
    name = head.split(";", 1)[0].strip().upper()
    return name, value.strip()


def to_ical_event(raw: dict[str, Any]) -> Event | None:
    """Build an ``ical.Event`` from a TimeTree event dict.

    Returns ``None`` for payloads that cannot be represented (missing
    uid/times) or that are intentionally skipped (memo, birthday).
    """
    if not is_calendar_relevant(raw):
        return None

    uid = raw.get("uuid")
    start_ms = raw.get("start_at")
    end_ms = raw.get("end_at")
    if not uid or start_ms is None or end_ms is None:
        _LOGGER.debug("Skipping event without uid/times: %r", raw.get("title"))
        return None

    all_day = bool(raw.get("all_day"))
    start_tz = _zone(raw.get("start_timezone"))
    end_tz = _zone(raw.get("end_timezone") or raw.get("start_timezone"))

    if all_day:
        dtstart: date | datetime = _ms_to_datetime(start_ms, start_tz).date()
        dtend: date | datetime = _ms_to_datetime(end_ms, end_tz).date() + timedelta(days=1)
        if dtend <= dtstart:
            dtend = dtstart + timedelta(days=1)
    else:
        dtstart = _ms_to_datetime(start_ms, start_tz)
        dtend = _ms_to_datetime(end_ms, end_tz)
        if dtend <= dtstart:
            dtend = dtstart + timedelta(minutes=1)

    rrule: Recur | None = None
    exdates: list[datetime | date] = []
    for line in raw.get("recurrences") or []:
        if not isinstance(line, str):
            continue
        name, value = _split_content_line(line)
        if name == "RRULE":
            try:
                rrule = Recur.from_rrule(value)
            except ValueError as err:
                _LOGGER.warning("Ignoring invalid RRULE %r for %s: %s", value, uid, err)
        elif name == "EXDATE":
            exdates.extend(_parse_exdates(value))
        # RDATE and unknown lines are ignored on purpose.

    if all_day:
        exdates = [d.date() if isinstance(d, datetime) else d for d in exdates]

    kwargs: dict[str, Any] = {
        "uid": str(uid),
        "summary": (raw.get("title") or "").strip() or "(ohne Titel)",
        "dtstart": dtstart,
        "dtend": dtend,
    }
    note = (raw.get("note") or "").strip()
    if note:
        kwargs["description"] = note
    location = (raw.get("location") or "").strip()
    if location:
        kwargs["location"] = location
    if rrule is not None:
        kwargs["rrule"] = rrule
    if exdates:
        kwargs["exdate"] = exdates

    try:
        return Event(**kwargs)
    except (ValueError, TypeError) as err:
        _LOGGER.warning("Could not build ical event for %s: %s", uid, err)
        return None
