"""Data update coordinator for TimeTree."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
import aiohttp

from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    TimeTreeAuthError,
    TimeTreeClient,
    TimeTreeConnectionError,
    TimeTreeSessionExpired,
)
from .const import (
    CONF_CALENDAR_ID,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SESSION_ID,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
)
from .store import EventStore

_LOGGER = logging.getLogger(__name__)

# How far the pre-expanded occurrence window reaches. The entity's "next
# event" is looked up in this window only; async_get_events still expands
# any range on demand.
WINDOW_PAST = timedelta(days=1)
WINDOW_FUTURE = timedelta(days=90)

_SESSION_KEY = f"{DOMAIN}_http_session"


def async_get_timetree_session(hass: HomeAssistant) -> aiohttp.ClientSession:
    """Return a TimeTree-only HTTP session without a cookie jar.

    Home Assistant's shared session keeps one cookie jar for every
    integration; TimeTree's session cookie must not live there. This session
    stores no cookies at all – the client sends its cookie explicitly – and is
    closed automatically when Home Assistant stops.
    """
    session = hass.data.get(_SESSION_KEY)
    if session is None or session.closed:
        session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
        hass.data[_SESSION_KEY] = session
    return session


class TimeTreeCoordinator(DataUpdateCoordinator[EventStore]):
    """Fetch TimeTree events incrementally and keep the session alive."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.data[CONF_CALENDAR_ID]}",
            update_interval=timedelta(minutes=minutes),
            config_entry=entry,
        )
        self._client = TimeTreeClient(
            async_get_timetree_session(hass),
            session_id=entry.data.get(CONF_SESSION_ID),
        )
        self._calendar_id: int = int(entry.data[CONF_CALENDAR_ID])
        self.store = EventStore()

    @property
    def calendar_id(self) -> int:
        """TimeTree calendar id this coordinator syncs."""
        return self._calendar_id

    async def _async_relogin(self) -> None:
        """Re-authenticate with stored credentials and persist the new cookie."""
        entry = self.config_entry
        try:
            session_id = await self._client.async_login(
                entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
            )
        except TimeTreeAuthError as err:
            raise ConfigEntryAuthFailed("TimeTree re-login rejected") from err
        except TimeTreeConnectionError as err:
            raise UpdateFailed(f"TimeTree re-login failed: {err}") from err

        self.hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_SESSION_ID: session_id}
        )
        # A fresh session means the old cursor may be stale – start over.
        self.store.reset()
        _LOGGER.info("TimeTree session renewed for calendar %s", self._calendar_id)

    async def _async_update_data(self) -> EventStore:
        """Pull changes since the last cursor; re-login once if the session died."""
        for attempt in (1, 2):
            try:
                result = await self._client.async_sync_all_events(
                    self._calendar_id, self.store.cursor
                )
            except TimeTreeSessionExpired:
                if attempt == 2:
                    raise ConfigEntryAuthFailed("TimeTree session could not be renewed")
                _LOGGER.debug("TimeTree session expired, attempting re-login")
                await self._async_relogin()
                continue
            except TimeTreeConnectionError as err:
                raise UpdateFailed(f"TimeTree unreachable: {err}") from err

            self.store.merge(result.events, result.since)
            # Labels are cheap (one small GET) and rarely change; refresh
            # them alongside the events so colours and names stay current.
            try:
                self.store.set_labels(await self._client.async_get_labels(self._calendar_id))
            except TimeTreeSessionExpired:
                raise
            except TimeTreeConnectionError as err:
                _LOGGER.debug("Keeping previous TimeTree labels: %s", err)
            # Recurrence expansion is CPU-bound and ``ical`` timelines are
            # lazy, so materialise the window here, off the event loop.
            now = dt_util.now()
            await self.hass.async_add_executor_job(
                self.store.build_window, now.tzinfo, now - WINDOW_PAST, now + WINDOW_FUTURE
            )
            _LOGGER.debug(
                "TimeTree sync: %d changes, %d events held, %d occurrences in window, cursor %s",
                len(result.events),
                self.store.count,
                len(self.store.window),
                result.since,
            )
            return self.store

        raise UpdateFailed("TimeTree sync gave up")  # pragma: no cover
