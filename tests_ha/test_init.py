"""Account entries, v1 → v2 migration and calendar selection (1.4.0)."""

from __future__ import annotations

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.timetree.const import DOMAIN

EMAIL = "Someone@Example.org"


def _v2_entry(calendars=("42", "7"), session="good") -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        unique_id="someone@example.org",
        title="someone@example.org",
        data={
            "email": EMAIL,
            "password": "pw",
            "session_id": session,
            "calendar_names": {"42": "Family", "7": "Work"},
        },
        options={"calendars": list(calendars)},
    )


def _timetree_entities(hass: HomeAssistant) -> dict[str, str]:
    registry = er.async_get(hass)
    return {
        e.unique_id: e.entity_id
        for e in registry.entities.values()
        if e.platform == DOMAIN and e.domain == "calendar" and "_label_" not in e.unique_id
    }


async def test_v1_entry_migrates_and_keeps_entity_id(hass: HomeAssistant, fake_client) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        unique_id="42",
        title="Family",
        data={
            "email": EMAIL,
            "password": "pw",
            "session_id": "good",
            "calendar_id": 42,
            "calendar_name": "Family",
        },
        options={"scan_interval": 15},
    )
    entry.add_to_hass(hass)
    er.async_get(hass).async_get_or_create(
        "calendar", DOMAIN, "timetree_42", config_entry=entry, suggested_object_id="familie_partner"
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.version == 2
    assert entry.unique_id == "someone@example.org"
    assert "calendar_id" not in entry.data
    assert entry.data["calendar_names"] == {"42": "Family"}
    assert entry.options == {"scan_interval": 15, "calendars": ["42"]}
    assert _timetree_entities(hass) == {"timetree_42": "calendar.familie_partner"}
    state = hass.states.get("calendar.familie_partner")
    assert state is not None and state.attributes["calendar_id"] == 42


async def test_second_v1_entry_of_same_account_keeps_working(hass: HomeAssistant, fake_client) -> None:
    first = _v2_entry(calendars=("42",))
    first.add_to_hass(hass)
    second = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        unique_id="7",
        data={"email": EMAIL, "password": "pw", "session_id": "good", "calendar_id": 7, "calendar_name": "Work"},
    )
    second.add_to_hass(hass)
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()
    assert second.state is ConfigEntryState.LOADED
    assert second.version == 2
    assert second.unique_id == "7"  # account id taken by the first entry


async def test_user_flow_selects_several_calendars(hass: HomeAssistant, fake_client) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": f" {EMAIL} ", "password": "pw"}
    )
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "calendars"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"calendars": []})
    assert result["errors"] == {"base": "no_calendar_selected"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"calendars": ["7", "42"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = result["result"]
    assert entry.unique_id == "someone@example.org"
    assert entry.options == {"calendars": ["7", "42"]}
    assert entry.data["calendar_names"] == {"42": "Family", "7": "Work"}
    await hass.async_block_till_done()

    assert set(_timetree_entities(hass)) == {"timetree_42", "timetree_7"}
    assert fake_client.login_calls == 1  # the flow's login; setup reuses the session


async def test_same_account_cannot_be_added_twice(hass: HomeAssistant, fake_client) -> None:
    _v2_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": "someone@EXAMPLE.org", "password": "pw"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert fake_client.login_calls == 0  # aborted before sending credentials


async def test_options_deselect_removes_calendar(hass: HomeAssistant, fake_client) -> None:
    entry = _v2_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert set(_timetree_entities(hass)) == {"timetree_42", "timetree_7"}

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"calendars": ["42"], "scan_interval": 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.options == {"calendars": ["42"], "scan_interval": 30}
    assert set(_timetree_entities(hass)) == {"timetree_42"}
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert [d.name for d in devices] == ["Family"]


async def test_options_picks_up_new_calendars(hass: HomeAssistant, fake_client) -> None:
    from custom_components.timetree.api import TimeTreeCalendarInfo

    entry = _v2_entry(calendars=("42",))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    fake_client.calendars.append(TimeTreeCalendarInfo(99, "Club"))
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"calendars": ["42", "99"], "scan_interval": 15}
    )
    await hass.async_block_till_done()
    assert entry.data["calendar_names"]["99"] == "Club"
    assert set(_timetree_entities(hass)) == {"timetree_42", "timetree_99"}


async def test_expired_session_is_renewed_once_for_all_calendars(hass: HomeAssistant, fake_client) -> None:
    entry = _v2_entry(session="expired")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert fake_client.login_calls == 1
    assert entry.data["session_id"] == "good"
    assert set(_timetree_entities(hass)) == {"timetree_42", "timetree_7"}


async def test_session_renewal_does_not_reload_the_entry(hass: HomeAssistant, fake_client) -> None:
    entry = _v2_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    account = hass.data[DOMAIN][entry.entry_id]

    hass.config_entries.async_update_entry(entry, data={**entry.data, "session_id": "rotated"})
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][entry.entry_id] is account  # same objects, no reload


async def test_diagnostics_are_redacted(hass: HomeAssistant, fake_client) -> None:
    from custom_components.timetree.diagnostics import async_get_config_entry_diagnostics

    entry = _v2_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)
    dumped = str(diag)
    for secret in ("Someone@Example.org", "pw'", "good", "Family", "Work", "Event 42"):
        assert secret not in dumped, secret
    assert [c["calendar_id"] for c in diag["calendars"]] == [42, 7]
