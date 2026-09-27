"""HTTP views used by the bundled TimeTree card.

Home Assistant's generic calendar REST API knows nothing about TimeTree's
colour labels, so the card asks this authenticated endpoint instead when the
calendar belongs to this integration:

    GET /api/timetree/events/<entity_id>?start=<iso>&end=<iso>

The response mirrors ``/api/calendars/<entity_id>`` (start/end/summary/…)
and adds ``label_id`` plus ``label`` ``{id, name, color}`` per occurrence.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from http import HTTPStatus
from typing import Any

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

from .api import TimeTreeBusy, TimeTreeError
from .comments import UID_RE
from .const import DOMAIN
from .coordinator import TimeTreeCoordinator, coordinator_for_entity

# Any authenticated user may call the view. Recurrence expansion is CPU-bound,
# so an unbounded range (e.g. 1900–9999) would be a cheap denial of service.
DEFAULT_RANGE = timedelta(days=7)
MAX_RANGE = timedelta(days=400)


def _coordinator_for(hass: HomeAssistant, entity_id: str) -> TimeTreeCoordinator | None:
    return coordinator_for_entity(hass, entity_id)


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
                    "media_count": store.media_count_of(item.uid) if item.uid else 0,
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


class TimeTreeCommentsView(HomeAssistantView):
    """Comments of one event, fetched from TimeTree on demand.

    Only uids of events that are part of the entity's calendar are accepted,
    so the proxy cannot be used to read anything else from the account.
    """

    url = "/api/timetree/comments/{entity_id}"
    name = "api:timetree:comments"
    requires_auth = True

    async def get(self, request: web.Request, entity_id: str) -> web.Response:
        """Return ``[{id, author, content, created_at}]`` for ``?uid=``."""
        hass: HomeAssistant = request.app["hass"]
        coordinator = _coordinator_for(hass, entity_id)
        if coordinator is None:
            return self.json_message("Not a TimeTree calendar", HTTPStatus.NOT_FOUND)
        uid = request.query.get("uid", "")
        if not UID_RE.match(uid) or not coordinator.data.has(uid):
            return self.json_message("Unknown event", HTTPStatus.NOT_FOUND)
        try:
            comments = await coordinator.async_get_comments(uid)
        except TimeTreeBusy:
            return self.json_message("Too many requests, try again shortly", HTTPStatus.TOO_MANY_REQUESTS)
        except TimeTreeError as err:
            _LOGGER.debug("TimeTree comments unavailable: %s", err)
            return self.json_message("TimeTree unavailable", HTTPStatus.BAD_GATEWAY)
        except Exception:  # noqa: BLE001 – incl. ConfigEntryAuthFailed/UpdateFailed from re-login
            _LOGGER.debug("TimeTree comments failed", exc_info=True)
            return self.json_message("TimeTree unavailable", HTTPStatus.BAD_GATEWAY)
        return self.json(comments)
