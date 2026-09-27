"""Diagnostics must be safe to attach to a public issue."""

from __future__ import annotations

import json

from custom_components.timetree.diag import REDACTED, build_diagnostics


def _payload():
    return build_diagnostics(
        entry_data={
            "email": "someone@example.org",
            "password": "hunter2-secret",
            "session_id": "sess-abcdef",
            "calendar_id": 42,
            "calendar_name": "Family",
        },
        options={"scan_interval": 15},
        raw_events=[
            {"uuid": "u1", "title": "Dentist Anna", "note": "bring card", "location": "Main Street 12",
             "all_day": False, "recurrences": ["RRULE:FREQ=WEEKLY"], "label_id": 3},
            {"uuid": "u2", "title": "Holiday", "all_day": True, "recurrences": None, "label_id": None},
        ],
        label_count=5,
        window_size=17,
        cursor=123,
        last_update_success=True,
        last_error=None,
        api_change_streak=0,
    )


def test_credentials_are_redacted():
    data = _payload()["entry"]["data"]
    assert data["email"] == REDACTED
    assert data["password"] == REDACTED
    assert data["session_id"] == REDACTED
    assert data["calendar_id"] == 42


def test_no_personal_event_content_leaks():
    dumped = json.dumps(_payload(), ensure_ascii=False)
    for secret in ("hunter2-secret", "sess-abcdef", "someone@example.org",
                   "Dentist Anna", "bring card", "Main Street 12", "Holiday"):
        assert secret not in dumped, secret


def test_counters_and_field_names_are_present():
    events = _payload()["events"]
    assert events["count"] == 2
    assert events["all_day"] == 1
    assert events["recurring"] == 1
    assert events["with_label"] == 1
    assert events["with_location"] == 1
    assert events["window_occurrences"] == 17
    assert "title" in events["field_names"] and "label_id" in events["field_names"]
