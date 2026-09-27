"""In-memory event store with incremental-sync merge semantics.

No Home Assistant imports. The coordinator feeds raw sync pages in; the
calendar entity reads a fully built ``ical.Calendar`` out.
"""

from __future__ import annotations

import logging
from datetime import datetime, tzinfo
from typing import Any

from ical.calendar import Calendar
from ical.event import Event
from ical.timeline import Timeline

from .api import TimeTreeLabel
from .event import is_deleted, to_ical_event

_LOGGER = logging.getLogger(__name__)


class EventStore:
    """Keep the latest known raw event per uuid and expose an ical Calendar."""

    def __init__(self) -> None:
        self._raw: dict[str, dict[str, Any]] = {}
        self._cursor: int | None = None
        self._calendar: Calendar | None = None
        # Expanded timelines are expensive to build (every recurrence gets
        # unrolled); cache them per timezone until the next merge.
        self._timelines: dict[str, Timeline] = {}
        # ``ical`` timelines are lazy: every iteration re-expands all series.
        # The coordinator therefore materialises a bounded window once, off the
        # event loop, and the entity's ``event`` property only reads this list.
        self._window: list[Event] = []
        self._labels: dict[int, TimeTreeLabel] = {}

    @property
    def labels(self) -> dict[int, TimeTreeLabel]:
        """Colour labels of the calendar, keyed by label id."""
        return self._labels

    def set_labels(self, labels: dict[int, TimeTreeLabel]) -> None:
        """Replace the known labels (does not invalidate the event window)."""
        self._labels = dict(labels)

    def label_id_of(self, uid: str) -> int | None:
        """Return the raw TimeTree label id attached to an event uid."""
        raw = self._raw.get(uid)
        if not raw:
            return None
        value = raw.get("label_id")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def label_of(self, uid: str) -> TimeTreeLabel | None:
        """Return the label object for an event uid, if any."""
        label_id = self.label_id_of(uid)
        return self._labels.get(label_id) if label_id is not None else None

    def alerts_of(self, uid: str) -> list[int]:
        """TimeTree reminders of an event as minutes before its start."""
        raw = self._raw.get(uid)
        alerts = raw.get("alerts") if raw else None
        if not isinstance(alerts, list):
            return []
        result: list[int] = []
        for value in alerts:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            minutes = int(value)
            # sanity bound: one year either way
            if -525_600 <= minutes <= 525_600 and minutes not in result:
                result.append(minutes)
        return result

    def raw_events(self) -> list[dict[str, Any]]:
        """Copies of the stored raw payloads (for diagnostics)."""
        return [dict(raw) for raw in self._raw.values()]

    @property
    def cursor(self) -> int | None:
        """Sync cursor to pass as ``since`` on the next fetch."""
        return self._cursor

    @property
    def count(self) -> int:
        """Number of live (non-deleted) events held."""
        return len(self._raw)

    def reset(self) -> None:
        """Drop everything; the next merge must be a full sync."""
        self._raw.clear()
        self._cursor = None
        self._calendar = None
        self._timelines.clear()
        self._window = []

    def merge(self, events: list[dict[str, Any]], cursor: int) -> None:
        """Apply one sync result: upsert live events, drop deleted ones."""
        for raw in events:
            uid = raw.get("uuid")
            if not uid:
                continue
            if is_deleted(raw):
                self._raw.pop(uid, None)
            else:
                self._raw[uid] = raw
        self._cursor = cursor
        self._calendar = None
        self._timelines.clear()

    def timeline(self, tz: tzinfo) -> Timeline:
        """Return a cached, recurrence-expanded timeline in the given timezone."""
        key = str(tz)
        if key not in self._timelines:
            self._timelines[key] = self.calendar().timeline_tz(tz)
        return self._timelines[key]

    def build_window(self, tz: tzinfo, start: datetime, end: datetime) -> list[Event]:
        """Materialise all occurrences between ``start`` and ``end`` (CPU-bound).

        Call this from an executor thread. The result is kept until the next
        merge/reset and served by :pyattr:`window`.
        """
        self._window = list(self.timeline(tz).overlapping(start, end))
        return self._window

    @property
    def window(self) -> list[Event]:
        """Occurrences from the last :meth:`build_window`, sorted by start."""
        return self._window

    def calendar(self) -> Calendar:
        """Return (and cache) an ical Calendar built from the stored events."""
        if self._calendar is None:
            cal = Calendar()
            for uid, raw in self._raw.items():
                # Hard boundary: one malformed payload must never take the
                # whole calendar (and with it the HA entity) down.
                try:
                    ev = to_ical_event(raw)
                except Exception as err:  # noqa: BLE001 – deliberately broad
                    _LOGGER.warning(
                        "Skipping TimeTree event %s (%r): %s",
                        uid,
                        raw.get("title"),
                        err,
                    )
                    continue
                if ev is not None:
                    cal.events.append(ev)
            self._calendar = cal
        return self._calendar
