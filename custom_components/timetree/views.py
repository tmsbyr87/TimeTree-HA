"""HTTP views used by the bundled TimeTree card.

Home Assistant's generic calendar REST API knows nothing about TimeTree's
colour labels, so the card asks this authenticated endpoint instead when the
calendar belongs to this integration:

    GET /api/timetree/events/<entity_id>?start=<iso>&end=<iso>

The response mirrors ``/api/calendars/<entity_id>`` (start/end/summary/…)
and adds ``label_id`` plus ``label`` ``{id, name, color}`` per occurrence.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from http import HTTPStatus
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import TimeTreeAccount, TimeTreeCoordinator

# Any authenticated user may call the view. Recurrence expansion is CPU-bound,
# so an unbounded range (e.g. 1900–9999) would be a cheap denial of service.
DEFAULT_RANGE = timedelta(days=7)
MAX_RANGE = timedelta(days=400)


def _coordinator_for(hass: HomeAssistant, entity_id: str) -> TimeTreeCoordinator | None:
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None or entry.platform != DOMAIN or not entry.config_entry_id:
        return None
    account: TimeTreeAccount | None = hass.data.get(DOMAIN, {}).get(entry.config_entry_id)
    if account is None:
        return None
    try:
        calendar_id = int(str(entry.unique_id).removeprefix(f"{DOMAIN}_"))
    except ValueError:
        return None
    return account.coordinators.get(calendar_id)


def _serialize_when(value: date | datetime) -> dict[str, str]:
    if isinstance(value, datetime):
        return {"dateTime": dt_util.as_local(value).isoformat()}
    return {"date": value.isoformat()}


def _parse_bound(raw: str | None, fallback: datetime) -> datetime:
    if not raw:
        return fallback
    parsed = dt_util.parse_datetime(raw)
    if parsed is None:
        return fallback
    if parsed.tzinfo is None:
        parsed = dt_util.as_local(parsed)
    return parsed


class TimeTreeEventsView(HomeAssistantView):
    """Events of one TimeTree calendar, enriched with label information."""

    url = "/api/timetree/events/{entity_id}"
    name = "api:timetree:events"
    requires_auth = True

    async def get(self, request: web.Request, entity_id: str) -> web.Response:
        """Return label-enriched occurrences overlapping start..end."""
        hass: HomeAssistant = request.app["hass"]
        coordinator = _coordinator_for(hass, entity_id)
        if coordinator is None:
            return self.json_message("Not a TimeTree calendar", HTTPStatus.NOT_FOUND)

        start = _parse_bound(request.query.get("start"), dt_util.now())
        end = _parse_bound(request.query.get("end"), start + DEFAULT_RANGE)
        if end <= start:
            return self.json_message("end must be after start", HTTPStatus.BAD_REQUEST)
        if end - start > MAX_RANGE:
            return self.json_message(
                f"range too large (max {MAX_RANGE.days} days)", HTTPStatus.BAD_REQUEST
            )

        store = coordinator.data
        timeline = store.timeline(start.tzinfo)
        items = await hass.async_add_executor_job(lambda: list(timeline.overlapping(start, end)))

        payload: list[dict[str, Any]] = []
        for item in items:
            label = store.label_of(item.uid) if item.uid else None
            payload.append(
                {
                    "uid": item.uid,
                    "summary": item.summary or "",
                    "description": item.description,
                    "location": item.location,
                    "start": _serialize_when(item.dtstart),
                    "end": _serialize_when(item.dtend),
                    "recurrence_id": item.recurrence_id,
                    "label_id": store.label_id_of(item.uid) if item.uid else None,
                    "label": (
                        {"id": label.label_id, "name": label.name, "color": label.color}
                        if label
                        else None
                    ),
                }
            )
        return self.json(payload)


class TimeTreeLabelsView(HomeAssistantView):
    """Labels of one TimeTree calendar (also available as entity attribute)."""

    url = "/api/timetree/labels/{entity_id}"
    name = "api:timetree:labels"
    requires_auth = True

    async def get(self, request: web.Request, entity_id: str) -> web.Response:
        """Return the calendar's labels."""
        hass: HomeAssistant = request.app["hass"]
        coordinator = _coordinator_for(hass, entity_id)
        if coordinator is None:
            return self.json_message("Not a TimeTree calendar", HTTPStatus.NOT_FOUND)
        labels = coordinator.data.labels
        return self.json(
            [
                {"id": lbl.label_id, "name": lbl.name, "color": lbl.color}
                for lbl in sorted(labels.values(), key=lambda l: l.name.lower())
            ]
        )
