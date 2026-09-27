"""Async client for the (unofficial) TimeTree web API.

This module deliberately has no Home Assistant imports so it can be unit-tested
in isolation. Endpoints and headers follow the behaviour of the TimeTree web
app as documented by the eoleedi/TimeTree-Exporter project.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

import aiohttp

from .const import (
    API_BASE_URL,
    API_ERROR_INVALID_CREDENTIALS,
    API_ERROR_RATE_LIMITED,
    API_USER_AGENT,
    SESSION_COOKIE,
)

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=30)


class TimeTreeError(Exception):
    """Base error for the TimeTree client."""


class TimeTreeConnectionError(TimeTreeError):
    """Network-level failure or unexpected server response."""


class TimeTreeAuthError(TimeTreeError):
    """Login failed for a reason other than wrong credentials."""


class TimeTreeInvalidCredentials(TimeTreeAuthError):
    """E-mail or password rejected."""


class TimeTreeRateLimited(TimeTreeAuthError):
    """Login attempts are being rate limited."""


class TimeTreeSessionExpired(TimeTreeError):
    """The stored session cookie is no longer accepted."""


@dataclass(frozen=True, slots=True)
class TimeTreeCalendarInfo:
    """Minimal description of a calendar the account has access to."""

    calendar_id: int
    name: str


@dataclass(frozen=True, slots=True)
class TimeTreeLabel:
    """A colour label defined in a TimeTree calendar."""

    label_id: int
    name: str
    color: str  # "#rrggbb"


def _color_to_hex(value: Any) -> str:
    """TimeTree sends colours as ints; normalise to a CSS hex string."""
    if isinstance(value, int):
        return f"#{value & 0xFFFFFF:06x}"
    if isinstance(value, str) and value:
        return value if value.startswith("#") else f"#{value}"
    return "#9e9e9e"


@dataclass(frozen=True, slots=True)
class SyncResult:
    """One page of the incremental event sync."""

    events: list[dict[str, Any]]
    since: int
    has_more: bool


class TimeTreeClient:
    """Thin async wrapper around the TimeTree web endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        session_id: str | None = None,
    ) -> None:
        self._session = session
        self._session_id = session_id

    @property
    def session_id(self) -> str | None:
        """Return the current session cookie value."""
        return self._session_id

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Timetreea": API_USER_AGENT,
        }

    def _cookies(self) -> dict[str, str]:
        if self._session_id is None:
            return {}
        return {SESSION_COOKIE: self._session_id}

    async def async_login(self, email: str, password: str) -> str:
        """Log in and store the returned session cookie.

        Returns the session id. Raises TimeTreeInvalidCredentials,
        TimeTreeRateLimited, TimeTreeAuthError or TimeTreeConnectionError.
        """
        payload = {
            "uid": email,
            "password": password,
            "uuid": uuid.uuid4().hex,
        }
        try:
            async with self._session.put(
                f"{API_BASE_URL}/auth/email/signin",
                json=payload,
                headers=self._headers(),
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status != 200:
                    code = await _extract_error_code(resp)
                    _LOGGER.debug("TimeTree login failed: HTTP %s code %s", resp.status, code)
                    if code == API_ERROR_INVALID_CREDENTIALS:
                        raise TimeTreeInvalidCredentials
                    if code == API_ERROR_RATE_LIMITED:
                        raise TimeTreeRateLimited
                    raise TimeTreeAuthError(f"HTTP {resp.status}")
                cookie = resp.cookies.get(SESSION_COOKIE)
        except aiohttp.ClientError as err:
            raise TimeTreeConnectionError(str(err)) from err

        if cookie is None or not cookie.value:
            raise TimeTreeAuthError("Login response carried no session cookie")

        self._session_id = cookie.value
        return self._session_id

    async def _get_json(self, path: str) -> dict[str, Any]:
        """GET a JSON endpoint using the stored session cookie."""
        if self._session_id is None:
            raise TimeTreeSessionExpired("No session available")
        try:
            async with self._session.get(
                f"{API_BASE_URL}{path}",
                headers=self._headers(),
                cookies=self._cookies(),
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status in (401, 403):
                    raise TimeTreeSessionExpired(f"HTTP {resp.status}")
                if resp.status != 200:
                    text = await resp.text()
                    raise TimeTreeConnectionError(f"HTTP {resp.status}: {text[:200]}")
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise TimeTreeConnectionError(str(err)) from err

    async def async_list_calendars(self) -> list[TimeTreeCalendarInfo]:
        """Return all calendars visible to the logged-in account."""
        data = await self._get_json("/calendars?since=0")
        result: list[TimeTreeCalendarInfo] = []
        for cal in data.get("calendars", []):
            cal_id = cal.get("id")
            if cal_id is None:
                continue
            result.append(
                TimeTreeCalendarInfo(
                    calendar_id=int(cal_id),
                    name=str(cal.get("name") or f"Calendar {cal_id}"),
                )
            )
        return result

    async def async_get_labels(self, calendar_id: int) -> dict[int, TimeTreeLabel]:
        """Return the calendar's colour labels keyed by label id.

        A missing or failing labels endpoint is not fatal – events still
        sync – so this returns an empty dict instead of raising for HTTP
        errors other than an expired session.
        """
        try:
            data = await self._get_json(f"/calendar/{calendar_id}/labels")
        except TimeTreeSessionExpired:
            raise
        except TimeTreeConnectionError as err:
            _LOGGER.debug("TimeTree labels unavailable for %s: %s", calendar_id, err)
            return {}
        result: dict[int, TimeTreeLabel] = {}
        for raw in data.get("calendar_labels") or data.get("labels") or []:
            label_id = raw.get("id")
            if label_id is None:
                continue
            try:
                key = int(label_id)
            except (TypeError, ValueError):
                continue
            result[key] = TimeTreeLabel(
                label_id=key,
                name=str(raw.get("name") or f"Label {key}").strip(),
                color=_color_to_hex(raw.get("color")),
            )
        return result

    async def async_sync_events(self, calendar_id: int, since: int | None) -> SyncResult:
        """Fetch one page of the event sync feed.

        ``since=None`` performs a full sync; afterwards pass the returned
        ``since`` cursor to receive only changes.
        """
        path = f"/calendar/{calendar_id}/events/sync"
        if since is not None:
            path = f"{path}?since={since}"
        data = await self._get_json(path)
        return SyncResult(
            events=list(data.get("events") or []),
            since=int(data.get("since") or 0),
            has_more=bool(data.get("chunk")),
        )

    async def async_sync_all_events(
        self, calendar_id: int, since: int | None
    ) -> SyncResult:
        """Follow ``chunk`` pages until the feed is exhausted."""
        page = await self.async_sync_events(calendar_id, since)
        events = list(page.events)
        cursor = page.since
        guard = 0
        while page.has_more and guard < 100:
            page = await self.async_sync_events(calendar_id, cursor)
            events.extend(page.events)
            cursor = page.since
            guard += 1
        return SyncResult(events=events, since=cursor, has_more=False)


async def _extract_error_code(resp: aiohttp.ClientResponse) -> int | None:
    """Pull the numeric TimeTree error code out of a failed response."""
    try:
        body = await resp.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    error = body.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        return int(code) if isinstance(code, int) else None
    return None
