"""Sensors, label calendars, reminders and the blueprint (1.5.0)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.timetree.const import DOMAIN

from .conftest import event_start


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        unique_id="someone@example.org",
        data={
            "email": "someone@example.org",
            "password": "pw",
            "session_id": "good",
            "calendar_names": {"42": "Family"},
        },
        options={"calendars": ["42"]},
    )


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    await hass.config.async_update(time_zone="Europe/Berlin")
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant, domain: str, unique_id: str) -> str | None:
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, unique_id)


async def test_sensors(hass: HomeAssistant, fake_client) -> None:
    await _setup(hass)
    next_id = _entity_id(hass, "sensor", "timetree_42_next_event")
    today_id = _entity_id(hass, "sensor", "timetree_42_events_today")
    assert next_id == "sensor.family_next_event"
    assert today_id == "sensor.family_events_today"

    nxt = hass.states.get(next_id)
    assert nxt.attributes["device_class"] == "timestamp"
    assert nxt.attributes["summary"] == "Event 42"
    assert nxt.attributes["label"] == "Kids"
    assert nxt.attributes["location"] == "Main Street 1"

    today = hass.states.get(today_id)
    # the fake event starts in two hours – still today unless the test runs just before midnight
    assert today.state in ("0", "1")
    assert today.attributes["more"] == 0


async def test_label_calendar_is_disabled_by_default(hass: HomeAssistant, fake_client) -> None:
    await _setup(hass)
    registry = er.async_get(hass)
    entity_id = _entity_id(hass, "calendar", "timetree_42_label_3")
    assert entity_id is not None
    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION

    # enable it and check it only contains events with that label
    registry.async_update_entity(entity_id, disabled_by=None)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.attributes["label_id"] == 3
    assert state.attributes["message"] == "Event 42"


async def test_new_label_appears_after_sync(hass: HomeAssistant, fake_client) -> None:
    from custom_components.timetree.api import TimeTreeLabel

    entry = await _setup(hass)
    fake_client.labels[9] = TimeTreeLabel(9, "Sport", "#ff0000")
    account = hass.data[DOMAIN][entry.entry_id]
    await account.coordinators[42].async_refresh()
    await hass.async_block_till_done()
    assert _entity_id(hass, "calendar", "timetree_42_label_9") is not None


async def test_reminder_event_fires_once(hass: HomeAssistant, fake_client, freezer) -> None:
    await _setup(hass)
    events = async_capture_events(hass, "timetree_reminder")

    due = event_start() - timedelta(minutes=60)
    for when in (due - timedelta(minutes=1), due, due + timedelta(minutes=1)):
        freezer.move_to(when)
        async_fire_time_changed(hass, when)
        await hass.async_block_till_done()

    assert len(events) == 1
    data = events[0].data
    assert data["summary"] == "Event 42"
    assert data["minutes_before"] == 60
    assert data["entity_id"] == "calendar.family"
    assert data["calendar_name"] == "Family"
    assert data["label"] == "Kids"


async def test_blueprint_is_installed_and_sends_notification(
    hass: HomeAssistant, fake_client, freezer
) -> None:
    target = Path(hass.config.path("blueprints", "automation", DOMAIN, "timetree_reminder.yaml"))
    try:
        await _setup(hass)
        assert target.exists()

        calls = async_mock_service(hass, "notify", "test_phone")
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": {
                    "use_blueprint": {
                        "path": "timetree/timetree_reminder.yaml",
                        "input": {
                            "calendars": ["calendar.family"],
                            "labels": ["Kids"],
                            "notify_services": ["notify.test_phone"],
                        },
                    }
                }
            },
        )
        await hass.async_block_till_done()

        due = event_start() - timedelta(minutes=60)
        freezer.move_to(due)
        async_fire_time_changed(hass, due)
        await hass.async_block_till_done()

        assert len(calls) == 1
        assert calls[0].data["title"] == "📅 Event 42"
        assert calls[0].data["message"] == f"{event_start().strftime('%H:%M')} · Main Street 1" or \
            calls[0].data["message"].endswith("· Main Street 1")
    finally:
        target.unlink(missing_ok=True)


async def test_blueprint_filters_other_labels(hass: HomeAssistant, fake_client, freezer) -> None:
    target = Path(hass.config.path("blueprints", "automation", DOMAIN, "timetree_reminder.yaml"))
    try:
        await _setup(hass)
        calls = async_mock_service(hass, "notify", "test_phone")
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": {
                    "use_blueprint": {
                        "path": "timetree/timetree_reminder.yaml",
                        "input": {"labels": ["Work"], "notify_services": ["notify.test_phone"]},
                    }
                }
            },
        )
        due = event_start() - timedelta(minutes=60)
        freezer.move_to(due)
        async_fire_time_changed(hass, due)
        await hass.async_block_till_done()
        assert calls == []
    finally:
        target.unlink(missing_ok=True)


async def test_blueprint_label_picker(hass: HomeAssistant, fake_client, freezer) -> None:
    target = Path(hass.config.path("blueprints", "automation", DOMAIN, "timetree_reminder.yaml"))
    try:
        await _setup(hass)
        label_cal = _entity_id(hass, "calendar", "timetree_42_label_3")
        calls = async_mock_service(hass, "notify", "test_phone")
        assert await async_setup_component(
            hass,
            "automation",
            {
                "automation": [
                    {
                        "id": "pick",
                        "use_blueprint": {
                            "path": "timetree/timetree_reminder.yaml",
                            "input": {"label_calendars": [label_cal], "notify_services": ["notify.test_phone"]},
                        },
                    },
                    {
                        "id": "other",
                        "use_blueprint": {
                            "path": "timetree/timetree_reminder.yaml",
                            "input": {"label_calendars": ["calendar.something_else"], "notify_services": ["notify.test_phone"]},
                        },
                    },
                ]
            },
        )
        due = event_start() - timedelta(minutes=60)
        freezer.move_to(due)
        async_fire_time_changed(hass, due)
        await hass.async_block_till_done()
        assert len(calls) == 1  # only the automation that picked the event's label
    finally:
        target.unlink(missing_ok=True)


async def test_reminder_carries_label_entity_id(hass: HomeAssistant, fake_client, freezer) -> None:
    await _setup(hass)
    events = async_capture_events(hass, "timetree_reminder")
    due = event_start() - timedelta(minutes=60)
    freezer.move_to(due)
    async_fire_time_changed(hass, due)
    await hass.async_block_till_done()
    assert events[0].data["label_entity_id"] == _entity_id(hass, "calendar", "timetree_42_label_3")


async def test_unedited_old_blueprint_is_upgraded_edited_one_kept(hass: HomeAssistant, fake_client) -> None:
    target = Path(hass.config.path("blueprints", "automation", DOMAIN, "timetree_reminder.yaml"))
    old = (Path(__file__).parent / "fixtures" / "timetree_reminder_1.5.0.yaml").read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_bytes(old)
        entry = await _setup(hass)
        assert b"label_calendars" in target.read_bytes()

        edited = old + b"\n# my own change\n"
        target.write_bytes(edited)
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert target.read_bytes() == edited
    finally:
        target.unlink(missing_ok=True)
