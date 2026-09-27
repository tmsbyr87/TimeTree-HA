"""Diagnostics download for TimeTree (Settings → Devices → TimeTree → Download diagnostics)."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import TimeTreeAccount
from .diag import build_diagnostics, calendar_diagnostics


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return a redacted snapshot that is safe to attach to a public issue."""
    account: TimeTreeAccount = hass.data[DOMAIN][entry.entry_id]
    calendars = []
    for calendar_id, coordinator in account.coordinators.items():
        store = coordinator.store
        calendars.append(
            calendar_diagnostics(
                calendar_id=calendar_id,
                raw_events=store.raw_events(),
                label_count=len(store.labels),
                window_size=len(store.window),
                cursor=store.cursor,
                last_update_success=coordinator.last_update_success,
                last_error=coordinator.last_error_kind,
                api_change_streak=coordinator.api_change_streak,
            )
        )
    return build_diagnostics(
        entry_data=dict(entry.data), options=dict(entry.options), calendars=calendars
    )
