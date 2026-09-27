"""Redacted diagnostics payload (no Home Assistant imports, unit-testable).

Diagnostics are meant to be attached to public GitHub issues, so the payload
contains structure and counters only: no credentials, no session, no event
titles, notes, locations or label names.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .const import CONF_EMAIL, CONF_PASSWORD, CONF_SESSION_ID

REDACTED = "**REDACTED**"
_SECRET_KEYS = {CONF_EMAIL, CONF_PASSWORD, CONF_SESSION_ID}


def redact_entry_data(data: dict[str, Any]) -> dict[str, Any]:
    """Return entry data with credentials replaced by a marker."""
    return {k: (REDACTED if k in _SECRET_KEYS else v) for k, v in data.items()}


def build_diagnostics(
    *,
    entry_data: dict[str, Any],
    options: dict[str, Any],
    raw_events: list[dict[str, Any]],
    label_count: int,
    window_size: int,
    cursor: int | None,
    last_update_success: bool,
    last_error: str | None,
    api_change_streak: int,
) -> dict[str, Any]:
    """Assemble the diagnostics dict from already-collected facts."""
    keys = Counter()
    all_day = recurring = with_label = with_location = 0
    for raw in raw_events:
        keys.update(raw.keys())
        all_day += bool(raw.get("all_day"))
        recurring += bool(raw.get("recurrences"))
        with_label += raw.get("label_id") is not None
        with_location += bool(raw.get("location"))

    return {
        "entry": {"data": redact_entry_data(entry_data), "options": dict(options)},
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
