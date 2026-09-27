"""Data update coordinator for TimeTree."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
import aiohttp

from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from homeassistant.helpers import issue_registry as ir

from .api import (
    TimeTreeApiChanged,
    TimeTreeAuthError,
    TimeTreeClient,
    TimeTreeConnectionError,
    TimeTreeSessionExpired,
)
from .const import (
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

# After this many consecutive "unexpected structure" answers we assume TimeTree
# changed its web API and raise a repair issue (one blip is not enough).
API_CHANGE_THRESHOLD = 3
ISSUE_API_CHANGED = "api_changed"
ISSUE_TRACKER_URL = "https://github.com/tmsbyr87/TimeTree-HA/issues"


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


class TimeTreeAccount:
    """One TimeTree login shared by all calendars of a config entry.

    Every calendar has its own coordinator, but they share one client and
    therefore one session cookie. When the session dies, the first calendar
    to notice logs in again; the others simply reuse the new cookie.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.client = TimeTreeClient(
            async_get_timetree_session(hass),
            session_id=entry.data.get(CONF_SESSION_ID),
        )
        self.coordinators: dict[int, TimeTreeCoordinator] = {}
        # Entry data changes on every session renewal; only option changes
        # (calendar selection, interval) should reload the entry.
        self.options_snapshot = dict(entry.options)
        self._login_lock = asyncio.Lock()

    async def async_relogin(self, failed_session_id: str | None) -> None:
        """Log in again unless another calendar already renewed the session."""
        async with self._login_lock:
            if self.client.session_id and self.client.session_id != failed_session_id:
                return
            entry = self.entry
            try:
                session_id = await self.client.async_login(
                    entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
                )
            except TimeTreeAuthError as err:
                raise ConfigEntryAuthFailed("TimeTree re-login rejected") from err
            except TimeTreeConnectionError as err:
                raise UpdateFailed(f"TimeTree re-login failed: {err}") from err
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_SESSION_ID: session_id}
            )
            _LOGGER.info("TimeTree session renewed")


class TimeTreeCoordinator(DataUpdateCoordinator[EventStore]):
    """Fetch one TimeTree calendar's events incrementally."""

    config_entry: ConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        account: TimeTreeAccount,
        calendar_id: int,
        calendar_name: str,
    ) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{calendar_id}",
            update_interval=timedelta(minutes=minutes),
            config_entry=entry,
        )
        self._account = account
        self._client = account.client
        self._calendar_id = int(calendar_id)
        self.calendar_name = calendar_name
        self.store = EventStore()
        self.api_change_streak = 0
        self.last_error_kind: str | None = None

    def _record_api_change(self, err: TimeTreeApiChanged) -> None:
        self.api_change_streak += 1
        self.last_error_kind = "api_changed"
        if self.api_change_streak == API_CHANGE_THRESHOLD:
            _LOGGER.error("TimeTree answered with an unknown structure %d times: %s", API_CHANGE_THRESHOLD, err)
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_API_CHANGED,
                is_fixable=False,
                is_persistent=False,
                severity=ir.IssueSeverity.ERROR,
                translation_key=ISSUE_API_CHANGED,
                learn_more_url=ISSUE_TRACKER_URL,
            )

    def _record_success(self) -> None:
        if self.api_change_streak >= API_CHANGE_THRESHOLD:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_API_CHANGED)
        self.api_change_streak = 0
        self.last_error_kind = None

    @property
    def calendar_id(self) -> int:
        """TimeTree calendar id this coordinator syncs."""
        return self._calendar_id

    async def _async_update_data(self) -> EventStore:
        """Pull changes since the last cursor; re-login once if the session died."""
        for attempt in (1, 2):
            try:
                result = await self._client.async_sync_all_events(
                    self._calendar_id, self.store.cursor
                )
            except TimeTreeSessionExpired:
                if attempt == 2:
                    self.last_error_kind = "auth"
                    raise ConfigEntryAuthFailed("TimeTree session could not be renewed")
                _LOGGER.debug("TimeTree session expired, attempting re-login")
                await self._account.async_relogin(self._client.session_id)
                # A fresh session means the old cursor may be stale – start over.
                self.store.reset()
                continue
            except TimeTreeApiChanged as err:
                self._record_api_change(err)
                raise UpdateFailed(f"TimeTree answered with an unknown structure: {err}") from err
            except TimeTreeConnectionError as err:
                self.last_error_kind = "connection"
                raise UpdateFailed(f"TimeTree unreachable: {err}") from err

            self.store.merge(result.events, result.since)
            self._record_success()
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
