"""In-memory event store with incremental-sync merge semantics.

No Home Assistant imports. The coordinator feeds raw sync pages in; the
calendar entity reads a fully built ``ical.Calendar`` out.
"""

from __future__ import annotations

from typing import Any

from ical.calendar import Calendar

from .event import is_deleted, to_ical_event


class EventStore:
    """Keep the latest known raw event per uuid and expose an ical Calendar."""

    def __init__(self) -> None:
        self._raw: dict[str, dict[str, Any]] = {}
        self._cursor: int | None = None
        self._calendar: Calendar | None = None

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

    def calendar(self) -> Calendar:
        """Return (and cache) an ical Calendar built from the stored events."""
        if self._calendar is None:
            cal = Calendar()
            for raw in self._raw.values():
                ev = to_ical_event(raw)
                if ev is not None:
                    cal.events.append(ev)
            self._calendar = cal
        return self._calendar
