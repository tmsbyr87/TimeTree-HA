"""Comment extraction for the event detail dialog (1.6.0)."""

from __future__ import annotations

from custom_components.timetree.comments import (
    UID_RE,
    comments_from_activities,
    member_names,
)

MEMBERS = [
    {"id": 11, "user_id": 901, "name": "Anna"},
    {"id": 12, "user_id": 902, "nickname": "Ben"},
    {"id": 13, "name": ""},
    {"id": None},
]

ACTIVITIES = [
    {"id": "c2", "type": 0, "author_id": 902, "created_at": 1_790_000_100_000, "attachment": {"content": " Second "}},
    {"id": "c1", "type": 0, "author_id": 11, "created_at": 1_790_000_000, "attachment": {"content": "First https://example.org"}},
    {"id": "h1", "type": 3, "author_id": 11, "created_at": 1_790_000_050_000, "attachment": {"content": "moved the event"}},
    {"id": "d1", "type": 0, "author_id": 11, "deactivated_at": 5, "attachment": {"content": "deleted"}},
    {"id": "e1", "type": 0, "author_id": 11, "attachment": {"content": "   "}},
    {"id": "x1", "type": 0, "author_id": 77, "attachment": "not a dict"},
    {"id": "u1", "type": 0, "author_id": 77, "created_at": True, "attachment": {"content": "who?"}},
]


def test_member_names_by_id_and_user_id():
    assert member_names(MEMBERS) == {"11": "Anna", "901": "Anna", "12": "Ben", "902": "Ben"}


def test_only_live_comments_oldest_first():
    comments = comments_from_activities(ACTIVITIES, member_names(MEMBERS))
    assert [c["id"] for c in comments] == ["u1", "c1", "c2"]
    first = comments[1]
    assert first["author"] == "Anna" and first["content"] == "First https://example.org"
    assert first["created_at"].startswith("2026-")
    assert comments[2]["author"] == "Ben" and comments[2]["content"] == "Second"
    assert comments[0]["author"] is None and comments[0]["created_at"] is None


def test_uid_pattern_blocks_path_tricks():
    assert UID_RE.match("0f8e2c1a-4b7d-4a55-9d61-3c2b1a0e9f77")
    for bad in ("../labels", "a/b", "", "x" * 65, "a?b=1", "a%2F"):
        assert not UID_RE.match(bad), bad
