"""Tests for the async TimeTree client (R1, R3, R4, R5)."""

from __future__ import annotations

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.timetree.api import (
    TimeTreeClient,
    TimeTreeConnectionError,
    TimeTreeInvalidCredentials,
    TimeTreeRateLimited,
    TimeTreeSessionExpired,
)
from custom_components.timetree.const import API_BASE_URL

LOGIN = f"{API_BASE_URL}/auth/email/signin"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.mark.asyncio
async def test_login_stores_session_cookie(session):
    with aioresponses() as m:
        m.put(LOGIN, status=200, payload={}, headers={"Set-Cookie": "_session_id=abc123; Path=/"})
        client = TimeTreeClient(session)
        sid = await client.async_login("a@b.de", "pw")
    assert sid == "abc123"
    assert client.session_id == "abc123"


@pytest.mark.asyncio
async def test_login_wrong_credentials(session):
    with aioresponses() as m:
        m.put(LOGIN, status=401, payload={"error": {"code": -702}})
        with pytest.raises(TimeTreeInvalidCredentials):
            await TimeTreeClient(session).async_login("a@b.de", "falsch")


@pytest.mark.asyncio
async def test_login_rate_limited(session):
    with aioresponses() as m:
        m.put(LOGIN, status=429, payload={"error": {"code": -495}})
        with pytest.raises(TimeTreeRateLimited):
            await TimeTreeClient(session).async_login("a@b.de", "pw")


@pytest.mark.asyncio
async def test_login_network_error(session):
    with aioresponses() as m:
        m.put(LOGIN, exception=aiohttp.ClientConnectionError("down"))
        with pytest.raises(TimeTreeConnectionError):
            await TimeTreeClient(session).async_login("a@b.de", "pw")


@pytest.mark.asyncio
async def test_list_calendars(session):
    with aioresponses() as m:
        m.get(
            f"{API_BASE_URL}/calendars?since=0",
            payload={"calendars": [{"id": 42, "name": "Familie"}, {"id": 7, "name": None}]},
        )
        cals = await TimeTreeClient(session, session_id="s").async_list_calendars()
    assert [(c.calendar_id, c.name) for c in cals] == [(42, "Familie"), (7, "Calendar 7")]


@pytest.mark.asyncio
async def test_expired_session_raises(session):
    with aioresponses() as m:
        m.get(f"{API_BASE_URL}/calendars?since=0", status=401, payload={})
        with pytest.raises(TimeTreeSessionExpired):
            await TimeTreeClient(session, session_id="old").async_list_calendars()


@pytest.mark.asyncio
async def test_no_session_raises_before_request(session):
    with pytest.raises(TimeTreeSessionExpired):
        await TimeTreeClient(session).async_list_calendars()


@pytest.mark.asyncio
async def test_get_labels_parses_int_colours(session):
    with aioresponses() as m:
        m.get(
            f"{API_BASE_URL}/calendar/42/labels",
            payload={"calendar_labels": [
                {"id": 1, "name": "Geburtstag", "color": 0xC8862A},
                {"id": 2, "name": "Urlaub", "color": "#3b9aa5"},
                {"id": "x", "name": "kaputt"},
            ]},
        )
        labels = await TimeTreeClient(session, session_id="s").async_get_labels(42)
    assert set(labels) == {1, 2}
    assert labels[1].name == "Geburtstag" and labels[1].color == "#c8862a"
    assert labels[2].color == "#3b9aa5"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (0xC8862A, "#c8862a"),
        ("#3B9AA5", "#3b9aa5"),
        ("3b9aa5", "#3b9aa5"),
        ("red; background:url(https://evil.example/x)", "#9e9e9e"),
        ("#fff", "#9e9e9e"),
        ("", "#9e9e9e"),
        (None, "#9e9e9e"),
        (True, "#9e9e9e"),
    ],
)
def test_label_colour_is_strictly_sanitised(raw, expected):
    from custom_components.timetree.api import _color_to_hex

    assert _color_to_hex(raw) == expected


@pytest.mark.asyncio
async def test_session_cookie_sent_as_header_not_via_jar(session):
    with aioresponses() as m:
        m.get(f"{API_BASE_URL}/calendars?since=0", payload={"calendars": []})
        await TimeTreeClient(session, session_id="abc123").async_list_calendars()
        (_, _), calls = next(iter(m.requests.items()))
        headers = calls[0].kwargs["headers"]
    assert headers["Cookie"] == "_session_id=abc123"
    assert "cookies" not in calls[0].kwargs
    assert len(session.cookie_jar) == 0


@pytest.mark.asyncio
async def test_error_message_does_not_leak_response_body(session):
    with aioresponses() as m:
        m.get(f"{API_BASE_URL}/calendars?since=0", status=500, body="secret calendar content")
        with pytest.raises(TimeTreeConnectionError) as exc:
            await TimeTreeClient(session, session_id="s").async_list_calendars()
    assert "secret" not in str(exc.value)


@pytest.mark.asyncio
async def test_get_labels_is_not_fatal_on_http_error(session):
    with aioresponses() as m:
        m.get(f"{API_BASE_URL}/calendar/42/labels", status=500, body="nope")
        labels = await TimeTreeClient(session, session_id="s").async_get_labels(42)
    assert labels == {}


@pytest.mark.asyncio
async def test_sync_follows_chunks(session):
    base = f"{API_BASE_URL}/calendar/42/events/sync"
    with aioresponses() as m:
        m.get(base, payload={"events": [{"uuid": "1"}], "chunk": True, "since": 10})
        m.get(f"{base}?since=10", payload={"events": [{"uuid": "2"}], "chunk": True, "since": 20})
        m.get(f"{base}?since=20", payload={"events": [{"uuid": "3"}], "chunk": False, "since": 30})
        result = await TimeTreeClient(session, session_id="s").async_sync_all_events(42, None)
    assert [e["uuid"] for e in result.events] == ["1", "2", "3"]
    assert result.since == 30
    assert result.has_more is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [{"data": []}, {"events": "nope"}, [], {"events": [], "since": "abc"}],
)
async def test_unknown_sync_structure_raises_api_changed(session, payload):
    from custom_components.timetree.api import TimeTreeApiChanged

    with aioresponses() as m:
        m.get(f"{API_BASE_URL}/calendar/42/events/sync", payload=payload)
        with pytest.raises(TimeTreeApiChanged):
            await TimeTreeClient(session, session_id="s").async_sync_events(42, None)


@pytest.mark.asyncio
async def test_unknown_calendars_structure_raises_api_changed(session):
    from custom_components.timetree.api import TimeTreeApiChanged

    with aioresponses() as m:
        m.get(f"{API_BASE_URL}/calendars?since=0", payload={"items": []})
        with pytest.raises(TimeTreeApiChanged):
            await TimeTreeClient(session, session_id="s").async_list_calendars()


@pytest.mark.asyncio
async def test_sync_incremental_uses_cursor(session):
    base = f"{API_BASE_URL}/calendar/42/events/sync"
    with aioresponses() as m:
        m.get(f"{base}?since=99", payload={"events": [], "chunk": False, "since": 120})
        result = await TimeTreeClient(session, session_id="s").async_sync_all_events(42, 99)
    assert result.events == []
    assert result.since == 120
