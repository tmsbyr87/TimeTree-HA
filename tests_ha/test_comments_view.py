"""Comment proxy used by the card's detail dialog (1.6.0)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .test_features import _setup


async def test_comments_for_known_event(hass: HomeAssistant, fake_client, hass_client) -> None:
    await _setup(hass)
    client = await hass_client()

    resp = await client.get("/api/timetree/comments/calendar.family?uid=42-1")
    assert resp.status == 200
    body = await resp.json()
    assert body == [
        {"id": "c1", "author": "Anna", "content": "Comment on 42-1", "created_at": body[0]["created_at"]}
    ]

    # second call within a minute is served from the cache
    await client.get("/api/timetree/comments/calendar.family?uid=42-1")
    assert fake_client.activity_calls == 1


async def test_comments_reject_foreign_or_malformed_uids(hass: HomeAssistant, fake_client, hass_client) -> None:
    await _setup(hass)
    client = await hass_client()
    for query in ("uid=not-in-calendar", "uid=..%2Flabels", "uid=", ""):
        resp = await client.get(f"/api/timetree/comments/calendar.family?{query}")
        assert resp.status in (400, 404), query  # HA itself rejects path tricks with 400
    resp = await client.get("/api/timetree/comments/calendar.other?uid=42-1")
    assert resp.status == 404
    assert fake_client.activity_calls == 0


async def test_comments_require_authentication(hass: HomeAssistant, fake_client, hass_client_no_auth) -> None:
    await _setup(hass)
    client = await hass_client_no_auth()
    resp = await client.get("/api/timetree/comments/calendar.family?uid=42-1")
    assert resp.status == 401


async def test_parallel_requests_share_one_upstream_call(hass: HomeAssistant, fake_client, hass_client) -> None:
    import asyncio

    await _setup(hass)
    client = await hass_client()
    responses = await asyncio.gather(
        *(client.get("/api/timetree/comments/calendar.family?uid=42-1") for _ in range(10))
    )
    assert [r.status for r in responses] == [200] * 10
    assert fake_client.activity_calls == 1


async def test_upstream_failures_are_cached(hass: HomeAssistant, fake_client, hass_client) -> None:
    from custom_components.timetree.api import TimeTreeConnectionError

    await _setup(hass)
    fake_client.activity_error = TimeTreeConnectionError("HTTP 500")
    client = await hass_client()
    first = await client.get("/api/timetree/comments/calendar.family?uid=42-1")
    second = await client.get("/api/timetree/comments/calendar.family?uid=42-1")
    assert first.status == 502
    assert second.status == 429
    assert fake_client.activity_calls == 1


async def test_on_demand_budget_limits_upstream_calls(hass: HomeAssistant, fake_client, hass_client) -> None:
    from custom_components.timetree.const import DOMAIN
    from custom_components.timetree.coordinator import ON_DEMAND_BUDGET

    entry = await _setup(hass)
    coordinator = hass.data[DOMAIN][entry.entry_id].coordinators[42]
    coordinator.store.merge([{"uuid": f"x{i}"} for i in range(ON_DEMAND_BUDGET + 5)], 2)
    client = await hass_client()
    statuses = [
        (await client.get(f"/api/timetree/comments/calendar.family?uid=x{i}")).status
        for i in range(ON_DEMAND_BUDGET + 5)
    ]
    assert 429 in statuses
    # members (1) + activities: never more upstream calls than the budget
    assert fake_client.activity_calls + 1 <= ON_DEMAND_BUDGET
