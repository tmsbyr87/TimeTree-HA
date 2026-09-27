"""Fixtures for the Home Assistant integration tests.

The TimeTree web API is replaced by ``FakeClient`` so the tests exercise the
real config flow, migration, coordinators and entities without network.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from homeassistant.util import dt as dt_util

from custom_components.timetree.api import (
    SyncResult,
    TimeTreeCalendarInfo,
    TimeTreeSessionExpired,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant load custom_components/timetree."""
    yield


def _event(uid: str, title: str) -> dict:
    start = dt_util.now().replace(microsecond=0) + timedelta(hours=2)
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
        "label_id": None,
    }


class FakeClient:
    """Stand-in for TimeTreeClient; state is shared per test via class attributes."""

    calendars = [TimeTreeCalendarInfo(42, "Family"), TimeTreeCalendarInfo(7, "Work")]
    valid_session = "good"
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

    async def async_get_labels(self, calendar_id: int) -> dict:
        return {}


@pytest.fixture
def fake_client():
    """Patch the TimeTree client everywhere it is constructed."""
    FakeClient.calendars = [TimeTreeCalendarInfo(42, "Family"), TimeTreeCalendarInfo(7, "Work")]
    FakeClient.valid_session = "good"
    FakeClient.login_calls = 0
    FakeClient.sync_calls = []
    with (
        patch("custom_components.timetree.coordinator.TimeTreeClient", FakeClient),
        patch("custom_components.timetree.config_flow.TimeTreeClient", FakeClient),
        patch("custom_components.timetree.coordinator.async_create_clientsession", return_value=None),
    ):
        yield FakeClient
