"""Calendar platform for TimeTree."""

from __future__ import annotations

from datetime import date, datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import CONF_CALENDAR_ID, CONF_CALENDAR_NAME, DOMAIN, STATIC_URL_BASE
from .coordinator import TimeTreeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the calendar entity for a configured TimeTree calendar."""
    coordinator: TimeTreeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TimeTreeCalendarEntity(coordinator, entry)])


def _to_calendar_event(item) -> CalendarEvent:
    """Map an expanded ``ical`` timeline item to a HA CalendarEvent."""
    start: date | datetime = item.dtstart
    end: date | datetime = item.dtend
    # HA requires timezone-aware datetimes for timed events.
    if isinstance(start, datetime) and start.tzinfo is None:
        start = dt_util.as_local(start.replace(tzinfo=dt_util.UTC))
    if isinstance(end, datetime) and end.tzinfo is None:
        end = dt_util.as_local(end.replace(tzinfo=dt_util.UTC))
    return CalendarEvent(
        summary=item.summary or "",
        start=start,
        end=end,
        description=item.description,
        location=item.location,
        uid=item.uid,
        recurrence_id=item.recurrence_id,
        rrule=item.rrule.as_rrule_str() if item.rrule else None,
    )


class TimeTreeCalendarEntity(CoordinatorEntity[TimeTreeCoordinator], CalendarEntity):
    """One TimeTree calendar exposed to Home Assistant."""

    _attr_has_entity_name = True
    _attr_name = None  # use the device/entry name
    # Served by the integration itself, see __init__._async_register_brand_assets.
    _attr_entity_picture = f"{STATIC_URL_BASE}/icon.png"

    def __init__(self, coordinator: TimeTreeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}_{entry.data[CONF_CALENDAR_ID]}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.data[CONF_CALENDAR_ID]))},
            name=entry.data.get(CONF_CALENDAR_NAME) or entry.title,
            manufacturer="TimeTree",
            model="Shared calendar",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Return the currently running or next upcoming event."""
        now = dt_util.now()
        timeline = self.coordinator.data.timeline(now.tzinfo)
        for item in timeline.active_after(now):
            return _to_calendar_event(item)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return all (expanded) events overlapping the requested window."""
        timeline = self.coordinator.data.timeline(start_date.tzinfo)
        return [
            _to_calendar_event(item)
            for item in timeline.overlapping(start_date, end_date)
        ]
