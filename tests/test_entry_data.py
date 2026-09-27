"""Config entry layout: v1 → v2 migration and calendar selection (1.4.0)."""

from __future__ import annotations

from custom_components.timetree.entry_data import (
    account_unique_id,
    merge_calendar_names,
    migrate_v1,
    selected_calendars,
)

V1_DATA = {
    "email": "someone@example.org",
    "password": "pw",
    "session_id": "s",
    "calendar_id": 42,
    "calendar_name": "Family",
}


def test_migrate_v1_keeps_credentials_and_selects_old_calendar():
    data, options = migrate_v1(V1_DATA, {"scan_interval": 30})
    assert data == {
        "email": "someone@example.org",
        "password": "pw",
        "session_id": "s",
        "calendar_names": {"42": "Family"},
    }
    assert options == {"scan_interval": 30, "calendars": ["42"]}


def test_migrated_entry_resolves_to_the_same_calendar():
    data, options = migrate_v1(V1_DATA, {})
    assert selected_calendars(data, options) == {42: "Family"}


def test_migrate_v1_without_name_uses_fallback():
    data, options = migrate_v1({**V1_DATA, "calendar_name": None}, {})
    assert selected_calendars(data, options) == {42: "Calendar 42"}


def test_selection_keeps_order_and_skips_garbage():
    data = {"calendar_names": {"1": "A", "2": "B"}}
    assert selected_calendars(data, {"calendars": ["2", "x", None, "1", "9"]}) == {
        2: "B",
        1: "A",
        9: "Calendar 9",
    }
    assert list(selected_calendars(data, {"calendars": ["2", "1"]})) == [2, 1]


def test_selection_defaults_to_all_known_calendars():
    assert selected_calendars({"calendar_names": {"1": "A", "2": "B"}}, {}) == {1: "A", 2: "B"}


def test_account_unique_id_normalises_email():
    assert account_unique_id("  Someone@Example.ORG ") == "someone@example.org"


def test_merge_calendar_names_updates_and_keeps():
    assert merge_calendar_names({"1": "Old", "3": "Gone"}, {1: "New", 2: "Two"}) == {
        "1": "New",
        "2": "Two",
        "3": "Gone",
    }
