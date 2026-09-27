"""Sensors per TimeTree calendar: events today and the next event."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .calendar import calendar_device_info
from .const import DOMAIN
from .coordinator import TimeTreeAccount, TimeTreeCoordinator
from .insights import as_datetime, describe, events_on, next_event

# Keep the state attributes small; the recorder stores them on every change.
MAX_LISTED_EVENTS = 20


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Two sensors per selected calendar."""
    account: TimeTreeAccount = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = []
    for coordinator in account.coordinators.values():
        entities += [TimeTreeTodaySensor(coordinator), TimeTreeNextEventSensor(coordinator)]
    async_add_entities(entities)


class _TimeTreeSensor(CoordinatorEntity[TimeTreeCoordinator], SensorEntity):
    _attr_has_entity_name = True
    _key: str

    def __init__(self, coordinator: TimeTreeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{coordinator.calendar_id}_{self._key}"
        self._attr_translation_key = self._key
        self._attr_device_info = calendar_device_info(coordinator)

    @property
    def available(self) -> bool:
        """Like the calendar: keep the last known events during TimeTree hiccups."""
        return super().available or self.coordinator.data.count > 0

    def _describe(self, item: Any) -> dict[str, Any]:
        store = self.coordinator.data
        return describe(item, dt_util.get_default_time_zone(), store.label_of(item.uid))


class TimeTreeTodaySensor(_TimeTreeSensor):
    """Number of events today; the events themselves as attribute."""

    _key = "events_today"
    _attr_icon = "mdi:calendar-today"

    def _today(self) -> list[Any]:
        now = dt_util.now()
        return events_on(self.coordinator.data.window, now.date(), now.tzinfo)

    @property
    def native_value(self) -> int:
        return len(self._today())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        events = self._today()
        return {
            "events": [
                {k: v for k, v in self._describe(item).items() if k != "description"}
                for item in events[:MAX_LISTED_EVENTS]
            ],
            "more": max(0, len(events) - MAX_LISTED_EVENTS),
        }


class TimeTreeNextEventSensor(_TimeTreeSensor):
    """Start of the next upcoming event (timestamp) with its details."""

    _key = "next_event"
    _attr_icon = "mdi:calendar-arrow-right"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def _next(self) -> Any | None:
        return next_event(self.coordinator.data.window, dt_util.now())

    @property
    def native_value(self) -> datetime | None:
        item = self._next()
        return as_datetime(item.dtstart, dt_util.get_default_time_zone()) if item else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self._next()
        return self._describe(item) if item else {}
