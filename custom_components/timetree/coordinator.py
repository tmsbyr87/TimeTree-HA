"""Data update coordinator for TimeTree."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
import aiohttp

from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_time_change

from .api import (
    TimeTreeApiChanged,
    TimeTreeAuthError,
    TimeTreeBusy,
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
    EVENT_REMINDER,
)
from .comments import comments_from_activities, media_candidates, member_names
from .insights import describe, due_reminders
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
REFRESH_COOLDOWN = timedelta(seconds=30)
COMMENT_CACHE = timedelta(minutes=1)
COMMENT_FAILURE_CACHE = timedelta(seconds=30)
COMMENT_CACHE_SIZE = 200
MEMBER_CACHE = timedelta(hours=1)
# Upstream budget for on-demand requests (comments) per account and minute,
# and how long an on-demand re-login waits after a failed one.
ON_DEMAND_BUDGET = 30
ON_DEMAND_WINDOW = timedelta(minutes=1)
RELOGIN_COOLDOWN = timedelta(minutes=5)
MAX_HINTS = 100
_HINT_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
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
        self._budget_window: datetime | None = None
        self._budget_used = 0
        self._relogin_failed_at: datetime | None = None

    def spend_budget(self) -> None:
        """Count one on-demand upstream request; raise TimeTreeBusy when exhausted."""
        now = dt_util.utcnow()
        if self._budget_window is None or now - self._budget_window >= ON_DEMAND_WINDOW:
            self._budget_window, self._budget_used = now, 0
        if self._budget_used >= ON_DEMAND_BUDGET:
            raise TimeTreeBusy("on-demand budget exhausted")
        self._budget_used += 1

    async def async_relogin_on_demand(self, failed_session_id: str | None) -> None:
        """Re-login triggered by a dashboard request – with a cooldown after failures.

        Scheduled syncs renew the session anyway; a dashboard must not be able
        to hammer TimeTree's login endpoint.
        """
        now = dt_util.utcnow()
        if self._relogin_failed_at and now - self._relogin_failed_at < RELOGIN_COOLDOWN:
            raise TimeTreeBusy("re-login cooling down")
        try:
            await self.async_relogin(failed_session_id)
        except Exception:
            self._relogin_failed_at = now
            raise
        self._relogin_failed_at = None

    def async_start_clock(self) -> None:
        """Tick every minute: fire due reminders and refresh time-based sensors."""
        self.entry.async_on_unload(
            async_track_time_change(self.hass, self._async_tick, second=0)
        )

    async def _async_tick(self, now: datetime) -> None:
        for coordinator in self.coordinators.values():
            coordinator.async_tick(dt_util.as_local(now))

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
            # Manual refreshes (card button, homeassistant.update_entity) are
            # bundled: TimeTree is asked at most every REFRESH_COOLDOWN.
            request_refresh_debouncer=Debouncer(
                hass, _LOGGER, cooldown=REFRESH_COOLDOWN.total_seconds(), immediate=True
            ),
        )
        self._account = account
        self.last_sync: datetime | None = None
        self._client = account.client
        self._calendar_id = int(calendar_id)
        self.calendar_name = calendar_name
        self.store = EventStore()
        self.api_change_streak = 0
        self.last_error_kind: str | None = None
        # Reminders due before setup are not replayed after a restart.
        self._last_tick = dt_util.now()
        self._fired: dict[tuple[str, str, int], datetime] = {}
        # Comments are fetched on demand (detail dialog) and cached briefly.
        self._members: dict[str, str] = {}
        self._members_at: datetime | None = None
        self._comments: dict[str, tuple[datetime, dict | None]] = {}
        self._pending: dict[str, asyncio.Task] = {}
        # Field names (never values) seen in on-demand answers, for diagnostics.
        self.shape_hints: dict[str, set[str]] = {}

    def _hint(self, key: str, items: list[dict]) -> None:
        bucket = self.shape_hints.setdefault(key, set())
        for item in items[:50]:
            for k in item:
                # plain field names only – never data that happens to be used as a key
                if len(bucket) < MAX_HINTS and isinstance(k, str) and _HINT_RE.match(k):
                    bucket.add(k)

    async def _async_with_session(self, call):
        """Run an on-demand API call, renewing the session once if needed."""
        try:
            return await call()
        except TimeTreeSessionExpired:
            await self._account.async_relogin_on_demand(self._client.session_id)
            return await call()

    def _cache_put(self, uid: str, at: datetime, comments: list[dict] | None) -> None:
        self._comments.pop(uid, None)
        self._comments[uid] = (at, comments)
        while len(self._comments) > COMMENT_CACHE_SIZE:
            self._comments.pop(next(iter(self._comments)))  # evict the oldest entry

    async def async_get_comments(self, uid: str) -> list[dict]:
        """Comments of one event (see :meth:`async_get_activity`)."""
        return (await self.async_get_activity(uid))["comments"]

    async def async_get_activity(self, uid: str) -> dict:
        """Comments (and media candidates) of one event of this calendar.

        Protects the shared TimeTree account against request floods from the
        dashboard: answers are cached, failures are cached briefly, parallel
        requests for the same event share one upstream call, and the account
        has an upstream budget (``TimeTreeBusy`` when exceeded).
        """
        now = dt_util.utcnow()
        cached = self._comments.get(uid)
        if cached:
            at, comments = cached
            if comments is not None and now - at < COMMENT_CACHE:
                return comments
            if comments is None and now - at < COMMENT_FAILURE_CACHE:
                raise TimeTreeBusy("recent failure")
        pending = self._pending.get(uid)
        if pending is None:
            pending = self.hass.async_create_task(self._async_fetch_comments(uid))
            self._pending[uid] = pending
            pending.add_done_callback(lambda _: self._pending.pop(uid, None))
        return await asyncio.shield(pending)

    async def _async_fetch_comments(self, uid: str) -> dict:
        now = dt_util.utcnow()
        try:
            if self._members_at is None or now - self._members_at > MEMBER_CACHE:
                self._account.spend_budget()
                members = await self._async_with_session(
                    lambda: self._client.async_get_members(self._calendar_id)
                )
                self._hint("member_keys", members)
                self._members = member_names(members)
                self._members_at = now
            self._account.spend_budget()
            activities = await self._async_with_session(
                lambda: self._client.async_get_activities(self._calendar_id, uid)
            )
        except TimeTreeBusy:
            raise
        except Exception:
            self._cache_put(uid, now, None)
            raise
        self._hint("activity_keys", activities)
        self._hint(
            "activity_attachment_keys",
            [a["attachment"] for a in activities if isinstance(a.get("attachment"), dict)],
        )
        result = {
            "comments": comments_from_activities(activities, self._members),
            "media": media_candidates(activities),
        }
        self._cache_put(uid, now, result)
        return result

    def async_tick(self, now: datetime) -> None:
        """Fire reminders that became due since the last tick, then refresh listeners."""
        previous, self._last_tick = self._last_tick, now
        for reminder in due_reminders(self.store.window, self.store.alerts_of, previous, now):
            if reminder.key in self._fired:
                continue
            self._fired[reminder.key] = reminder.fire_at
            self.hass.bus.async_fire(EVENT_REMINDER, self.reminder_data(reminder))
        cutoff = now - timedelta(days=1)
        self._fired = {k: v for k, v in self._fired.items() if v > cutoff}
        # "today" and "next event" move with the clock, not only with syncs.
        self.async_update_listeners()

    def reminder_data(self, reminder) -> dict:
        """Payload of a ``timetree_reminder`` event."""
        item = reminder.item
        data = describe(item, self._last_tick.tzinfo, self.store.label_of(item.uid))
        registry = er.async_get(self.hass)
        label_id = data.get("label_id")
        data.update(
            entity_id=registry.async_get_entity_id(
                "calendar", DOMAIN, f"{DOMAIN}_{self._calendar_id}"
            ),
            # the label's own calendar entity – lets automations pick labels
            # from a list instead of typing their names
            label_entity_id=(
                registry.async_get_entity_id(
                    "calendar", DOMAIN, f"{DOMAIN}_{self._calendar_id}_label_{label_id}"
                )
                if label_id is not None
                else None
            ),
            calendar_id=self._calendar_id,
            calendar_name=self.calendar_name,
            minutes_before=reminder.minutes_before,
        )
        return data

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
            self.last_sync = dt_util.utcnow()
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
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug("TimeTree events with media (sample): %s", self.store.uids_with_media())
            _LOGGER.debug(
                "TimeTree sync: %d changes, %d events held, %d occurrences in window, cursor %s",
                len(result.events),
                self.store.count,
                len(self.store.window),
                result.since,
            )
            return self.store

        raise UpdateFailed("TimeTree sync gave up")  # pragma: no cover


def coordinator_for_entity(hass: HomeAssistant, entity_id: str) -> TimeTreeCoordinator | None:
    """Coordinator behind a TimeTree calendar entity (incl. label calendars)."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or entry.platform != DOMAIN or not entry.config_entry_id:
        return None
    account: TimeTreeAccount | None = hass.data.get(DOMAIN, {}).get(entry.config_entry_id)
    if account is None:
        return None
    # "timetree_<calendar>" or "timetree_<calendar>_label_<label>" / "_<sensor>"
    try:
        calendar_id = int(str(entry.unique_id).split("_")[1])
    except (IndexError, ValueError):
        return None
    return account.coordinators.get(calendar_id)
