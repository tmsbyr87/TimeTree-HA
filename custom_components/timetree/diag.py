"""Redacted diagnostics payload (no Home Assistant imports, unit-testable).

Diagnostics are meant to be attached to public GitHub issues, so the payload
contains structure and counters only: no credentials, no session, no calendar
names, no event titles, notes, locations or label names.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .const import (
    CONF_CALENDAR_NAME,
    CONF_CALENDAR_NAMES,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SESSION_ID,
)

REDACTED = "**REDACTED**"
_SECRET_KEYS = {CONF_EMAIL, CONF_PASSWORD, CONF_SESSION_ID, CONF_CALENDAR_NAME}


def redact_entry_data(data: dict[str, Any]) -> dict[str, Any]:
    """Return entry data with credentials and calendar names replaced by a marker."""
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if key in _SECRET_KEYS:
            redacted[key] = REDACTED
        elif key == CONF_CALENDAR_NAMES and isinstance(value, dict):
            # keep the ids (they help debugging), drop the names
            redacted[key] = {cal_id: REDACTED for cal_id in value}
        else:
            redacted[key] = value
    return redacted


def calendar_diagnostics(
    *,
    calendar_id: int,
    raw_events: list[dict[str, Any]],
    label_count: int,
    window_size: int,
    cursor: int | None,
    last_update_success: bool,
    last_error: str | None,
    api_change_streak: int,
) -> dict[str, Any]:
    """Counters for one synced calendar."""
    keys: Counter[str] = Counter()
    all_day = recurring = with_label = with_location = 0
    for raw in raw_events:
        keys.update(raw.keys())
        all_day += bool(raw.get("all_day"))
        recurring += bool(raw.get("recurrences"))
        with_label += raw.get("label_id") is not None
        with_location += bool(raw.get("location"))

    return {
        "calendar_id": calendar_id,
        "sync": {
            "last_update_success": last_update_success,
            "last_error": last_error,
            "api_change_streak": api_change_streak,
            "cursor_present": cursor is not None,
        },
        "events": {
            "count": len(raw_events),
            "all_day": all_day,
            "recurring": recurring,
            "with_label": with_label,
            "with_location": with_location,
            "window_occurrences": window_size,
            # field names only – tells us when TimeTree adds/removes fields
            "field_names": sorted(keys),
        },
        "labels": {"count": label_count},
    }


def build_diagnostics(
    *,
    entry_data: dict[str, Any],
    options: dict[str, Any],
    calendars: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble the diagnostics dict from already-collected facts."""
    return {
        "entry": {"data": redact_entry_data(entry_data), "options": dict(options)},
        "calendars": calendars,
    }
