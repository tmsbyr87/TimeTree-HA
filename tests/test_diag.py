"""Diagnostics must be safe to attach to a public issue."""

from __future__ import annotations

import json

from custom_components.timetree.diag import REDACTED, build_diagnostics, calendar_diagnostics


def _calendar():
    return calendar_diagnostics(
        calendar_id=42,
        raw_events=[
            {"uuid": "u1", "title": "Dentist Anna", "note": "bring card", "location": "Main Street 12",
             "all_day": False, "recurrences": ["RRULE:FREQ=WEEKLY"], "label_id": 3, "alerts": [15],
             "files": [{"url": "https://secret.example/photo.jpg", "id": 5}], "attachment": {"checklist": ["milk"]}},
            {"uuid": "u2", "title": "Holiday", "all_day": True, "recurrences": None, "label_id": None},
        ],
        label_count=5,
        window_size=17,
        cursor=123,
        last_update_success=True,
        last_error=None,
        api_change_streak=0,
        shape_hints={"activity_keys": {"type", "attachment"}},
    )


def _payload():
    return build_diagnostics(
        entry_data={
            "email": "someone@example.org",
            "password": "hunter2-secret",
            "session_id": "sess-abcdef",
            "calendar_names": {"42": "Smith Family", "7": "Work"},
        },
        options={"scan_interval": 15, "calendars": ["42"]},
        calendars=[_calendar()],
    )


def test_credentials_and_calendar_names_are_redacted():
    data = _payload()["entry"]["data"]
    assert data["email"] == REDACTED
    assert data["password"] == REDACTED
    assert data["session_id"] == REDACTED
    assert data["calendar_names"] == {"42": REDACTED, "7": REDACTED}


def test_v1_calendar_name_is_redacted_too():
    payload = build_diagnostics(
        entry_data={"calendar_id": 42, "calendar_name": "Smith Family"}, options={}, calendars=[]
    )
    assert payload["entry"]["data"] == {"calendar_id": 42, "calendar_name": REDACTED}


def test_no_personal_content_leaks():
    dumped = json.dumps(_payload(), ensure_ascii=False)
    for secret in ("hunter2-secret", "sess-abcdef", "someone@example.org", "Smith Family", "Work",
                   "Dentist Anna", "bring card", "Main Street 12", "Holiday",
                   "secret.example", "milk"):
        assert secret not in dumped, secret


def test_counters_and_field_names_are_present():
    cal = _payload()["calendars"][0]
    assert cal["calendar_id"] == 42
    events = cal["events"]
    assert events["count"] == 2
    assert events["all_day"] == 1
    assert events["recurring"] == 1
    assert events["with_label"] == 1
    assert events["with_location"] == 1
    assert events["with_alerts"] == 1
    assert events["window_occurrences"] == 17
    assert "title" in events["field_names"] and "label_id" in events["field_names"]


def test_shapes_report_key_names_only():
    shapes = _payload()["calendars"][0]["shapes"]
    assert shapes["event_files_keys"] == ["id", "url"]
    assert shapes["event_attachment_keys"] == ["checklist"]
    assert shapes["activity_keys"] == ["attachment", "type"]
