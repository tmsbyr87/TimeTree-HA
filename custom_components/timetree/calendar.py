"""Calendar platform for TimeTree."""

from __future__ import annotations

from datetime import date, datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, STATIC_URL_BASE
from .coordinator import TimeTreeAccount, TimeTreeCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one calendar entity per selected TimeTree calendar."""
    account: TimeTreeAccount = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        TimeTreeCalendarEntity(coordinator) for coordinator in account.coordinators.values()
    )

    # One (disabled by default) calendar per TimeTree label; labels created
    # later in TimeTree show up after the next sync.
    for coordinator in account.coordinators.values():
        known: set[int] = set()

        @callback
        def _add_new_labels(coordinator: TimeTreeCoordinator = coordinator, known: set[int] = known) -> None:
            new = [lid for lid in coordinator.data.labels if lid not in known]
            if new:
                known.update(new)
                async_add_entities(TimeTreeLabelCalendarEntity(coordinator, lid) for lid in new)

        _add_new_labels()
        entry.async_on_unload(coordinator.async_add_listener(_add_new_labels))


def calendar_device_info(coordinator: TimeTreeCoordinator) -> DeviceInfo:
    """Device shared by all entities of one TimeTree calendar."""
    return DeviceInfo(
        identifiers={(DOMAIN, str(coordinator.calendar_id))},
        name=coordinator.calendar_name,
        manufacturer="TimeTree",
        model="Shared calendar",
        entry_type=DeviceEntryType.SERVICE,
    )


def _end_as_datetime(item, tz) -> datetime:
    """Exclusive end of an occurrence as an aware datetime (dates → local midnight)."""
    end = item.dtend
    if isinstance(end, datetime):
        return end if end.tzinfo else end.replace(tzinfo=tz)
    return datetime.combine(end, datetime.min.time(), tzinfo=tz)


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
    # changes every sync; not worth a database row each time
    _unrecorded_attributes = frozenset({"last_sync", "labels"})
    # Served by the integration itself, see __init__._async_register_brand_assets.
    _attr_entity_picture = f"{STATIC_URL_BASE}/icon.png"

    def __init__(self, coordinator: TimeTreeCoordinator) -> None:
        super().__init__(coordinator)
        # Same ids as in 1.0–1.3 (one entry per calendar), so migrated
        # entities keep their entity_id, history and dashboard references.
        self._attr_unique_id = f"{DOMAIN}_{coordinator.calendar_id}"
        self._attr_device_info = calendar_device_info(coordinator)

    @property
    def available(self) -> bool:
        """Stay available with the last known events while TimeTree hiccups.

        A failed refresh (network, or TimeTree changing its API) should not
        blank the family calendar; the repair issue tells the user what is
        going on. Only an entry that never synced is unavailable.
        """
        return super().available or self.coordinator.data.count > 0

    @property
    def extra_state_attributes(self) -> dict:
        """Expose the calendar's labels so the bundled card can offer filters."""
        labels = self.coordinator.data.labels
        last_sync = self.coordinator.last_sync
        return {
            "calendar_id": self.coordinator.calendar_id,
            # changes after every successful sync – lets the card reload at once
            "last_sync": last_sync.isoformat() if last_sync else None,
            "labels": [
                {"id": lbl.label_id, "name": lbl.name, "color": lbl.color}
                for lbl in sorted(labels.values(), key=lambda l: l.name.lower())
            ],
        }

    def _includes(self, item) -> bool:
        """Whether an occurrence belongs to this entity (all of them here)."""
        return True

    @property
    def event(self) -> CalendarEvent | None:
        """Return the currently running or next upcoming event."""
        now = dt_util.now()
        # The window is pre-expanded by the coordinator (executor thread) and
        # sorted by start, so this is a cheap scan on the event loop.
        for item in self.coordinator.data.window:
            if _end_as_datetime(item, now.tzinfo) > now and self._includes(item):
                return _to_calendar_event(item)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return all (expanded) events overlapping the requested window."""
        timeline = self.coordinator.data.timeline(start_date.tzinfo)
        # Expansion is CPU-bound – keep it off the event loop.
        items = await hass.async_add_executor_job(
            lambda: list(timeline.overlapping(start_date, end_date))
        )
        return [_to_calendar_event(item) for item in items if self._includes(item)]


class TimeTreeLabelCalendarEntity(TimeTreeCalendarEntity):
    """Only the events carrying one TimeTree label (e.g. "Kids", "Work").

    Disabled by default – enable the labels you want to automate on.
    """

    _attr_entity_registry_enabled_default = False
    _attr_entity_picture = None

    def __init__(self, coordinator: TimeTreeCoordinator, label_id: int) -> None:
        super().__init__(coordinator)
        self._label_id = label_id
        self._attr_unique_id = f"{DOMAIN}_{coordinator.calendar_id}_label_{label_id}"

    @property
    def name(self) -> str:
        label = self.coordinator.data.labels.get(self._label_id)
        return label.name if label else f"Label {self._label_id}"

    @property
    def available(self) -> bool:
        return super().available and self._label_id in self.coordinator.data.labels

    @property
    def icon(self) -> str:
        return "mdi:label"

    def _includes(self, item) -> bool:
        return bool(item.uid) and self.coordinator.data.label_id_of(item.uid) == self._label_id

    @property
    def extra_state_attributes(self) -> dict:
        label = self.coordinator.data.labels.get(self._label_id)
        return {
            "calendar_id": self.coordinator.calendar_id,
            "label_id": self._label_id,
            "label_color": label.color if label else None,
        }
