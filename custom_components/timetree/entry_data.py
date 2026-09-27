"""Config entry layout helpers (no Home Assistant imports, unit-testable).

Version 1 entries held exactly one calendar. Version 2 holds one TimeTree
account with any number of calendars; the selection lives in the options so
it can be changed later without signing in again.
"""

from __future__ import annotations

from typing import Any

from .const import (
    CONF_CALENDAR_ID,
    CONF_CALENDAR_NAME,
    CONF_CALENDAR_NAMES,
    CONF_CALENDARS,
    CONF_EMAIL,
)


def fallback_name(calendar_id: int | str) -> str:
    """Name used when TimeTree did not tell us one."""
    return f"Calendar {calendar_id}"


def account_unique_id(email: str) -> str:
    """Unique id of an account entry – one entry per TimeTree login."""
    return email.strip().lower()


def migrate_v1(data: dict[str, Any], options: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Turn a single-calendar v1 entry into an account entry (v2).

    Entity and device identifiers are derived from the calendar id and do not
    change, so existing entity ids, history and dashboards keep working.
    """
    calendar_id = str(data[CONF_CALENDAR_ID])
    name = data.get(CONF_CALENDAR_NAME) or fallback_name(calendar_id)
    new_data = {k: v for k, v in data.items() if k not in (CONF_CALENDAR_ID, CONF_CALENDAR_NAME)}
    new_data[CONF_CALENDAR_NAMES] = {calendar_id: name}
    new_options = {**options, CONF_CALENDARS: [calendar_id]}
    return new_data, new_options


def selected_calendars(data: dict[str, Any], options: dict[str, Any]) -> dict[int, str]:
    """Calendars to sync as ``{id: name}``, in the order the user chose them."""
    names: dict[str, str] = data.get(CONF_CALENDAR_NAMES) or {}
    chosen = options.get(CONF_CALENDARS)
    if chosen is None:
        chosen = list(names)
    result: dict[int, str] = {}
    for raw in chosen:
        try:
            calendar_id = int(raw)
        except (TypeError, ValueError):
            continue
        result[calendar_id] = names.get(str(calendar_id)) or fallback_name(calendar_id)
    return result


def merge_calendar_names(old: dict[str, str], fresh: dict[int, str]) -> dict[str, str]:
    """Update stored names with what TimeTree reports now, keep unknown ones."""
    merged = dict(old)
    merged.update({str(k): v for k, v in fresh.items()})
    return merged


def account_email(data: dict[str, Any]) -> str:
    """Stored login e-mail."""
    return str(data.get(CONF_EMAIL, ""))
