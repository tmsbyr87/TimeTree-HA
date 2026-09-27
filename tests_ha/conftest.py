"""Fixtures for the Home Assistant integration tests.

The TimeTree web API is replaced by ``FakeClient`` so the tests exercise the
real config flow, migration, coordinators and entities without network.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from homeassistant.util import dt as dt_util

from custom_components.timetree.api import (
    SyncResult,
    TimeTreeCalendarInfo,
    TimeTreeLabel,
    TimeTreeSessionExpired,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/timetree."""
    yield


_START: list[datetime] = []


def event_start() -> datetime:
    """Start of the fake events: two hours after the test began, on a full minute.

    Fixed per test so that syncs triggered while the clock is moved forward
    do not shift the event along with it.
    """
    return _START[0]


def _event(uid: str, title: str) -> dict:
    start = event_start()
    ms = int(start.timestamp() * 1000)
    return {
        "uuid": uid,
        "title": title,
        "all_day": False,
        "start_at": ms,
        "end_at": ms + 3_600_000,
        "start_timezone": "UTC",
        "end_timezone": "UTC",
        "type": 0,
        "category": 1,
        "recurrences": None,
        "deactivated_at": None,
        "label_id": 3,
        "alerts": [60],
        "location": "Main Street 1",
    }


class FakeClient:
    """Stand-in for TimeTreeClient; state is shared per test via class attributes."""

    calendars = [TimeTreeCalendarInfo(42, "Family"), TimeTreeCalendarInfo(7, "Work")]
    valid_session = "good"
    labels = {3: TimeTreeLabel(3, "Kids", "#3b9aa5")}
    login_calls = 0
    sync_calls: list[tuple[int, str | None]] = []

    def __init__(self, session=None, session_id: str | None = None) -> None:
        self._session_id = session_id

    @property
    def session_id(self) -> str | None:
        return self._session_id

    async def async_login(self, email: str, password: str) -> str:
        FakeClient.login_calls += 1
        self._session_id = FakeClient.valid_session
        return self._session_id

    async def async_list_calendars(self) -> list[TimeTreeCalendarInfo]:
        return list(FakeClient.calendars)

    async def async_sync_all_events(self, calendar_id: int, since: int | None) -> SyncResult:
        FakeClient.sync_calls.append((calendar_id, self._session_id))
        if self._session_id != FakeClient.valid_session:
            raise TimeTreeSessionExpired("expired")
        return SyncResult(events=[_event(f"{calendar_id}-1", f"Event {calendar_id}")], since=1, has_more=False)

    activity_calls = 0

    async def async_get_members(self, calendar_id: int) -> list[dict]:
        return [{"id": 11, "user_id": 901, "name": "Anna"}]

    activity_error: Exception | None = None

    async def async_get_activities(self, calendar_id: int, event_uuid: str) -> list[dict]:
        FakeClient.activity_calls += 1
        await asyncio.sleep(0.01)
        if FakeClient.activity_error is not None:
            raise FakeClient.activity_error
        return [
            {"id": "c1", "type": 0, "author_id": 901, "created_at": 1_790_000_000_000,
             "attachment": {"content": f"Comment on {event_uuid}"}},
            {"id": "h1", "type": 3, "author_id": 901, "attachment": {"content": "history"}},
        ]

    async def async_get_labels(self, calendar_id: int) -> dict:
        return dict(FakeClient.labels)


@pytest.fixture
def fake_client():
    """Patch the TimeTree client everywhere it is constructed."""
    FakeClient.calendars = [TimeTreeCalendarInfo(42, "Family"), TimeTreeCalendarInfo(7, "Work")]
    _START[:] = [dt_util.now().replace(second=0, microsecond=0) + timedelta(hours=2)]
    FakeClient.valid_session = "good"
    FakeClient.labels = {3: TimeTreeLabel(3, "Kids", "#3b9aa5")}
    FakeClient.login_calls = 0
    FakeClient.activity_calls = 0
    FakeClient.activity_error = None
    FakeClient.sync_calls = []
    with (
        patch("custom_components.timetree.coordinator.TimeTreeClient", FakeClient),
        patch("custom_components.timetree.config_flow.TimeTreeClient", FakeClient),
        patch("custom_components.timetree.coordinator.async_create_clientsession", return_value=None),
    ):
        yield FakeClient
