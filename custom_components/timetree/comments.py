"""Turn TimeTree's raw activity feed into plain comments (no HA imports)."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

# TimeTree event uuids are hex/dash strings; anything else never reaches the API.
UID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ACTIVITY_TYPE_COMMENT = 0
MAX_COMMENTS = 100
MAX_LENGTH = 4000


def _timestamp(value: Any) -> str | None:
    """ISO timestamp from TimeTree's epoch value (milliseconds or seconds)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    seconds = value / 1000 if value > 10**11 else value
    try:
        return datetime.fromtimestamp(seconds, UTC).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def member_names(members: list[dict[str, Any]]) -> dict[str, str]:
    """Map every id a member may be referenced by to a display name."""
    names: dict[str, str] = {}
    for member in members:
        name = member.get("name") or member.get("nickname") or member.get("display_name")
        if not isinstance(name, str) or not name.strip():
            continue
        for key in ("id", "user_id"):
            if member.get(key) is not None:
                names[str(member[key])] = name.strip()
    return names


def comments_from_activities(
    activities: list[dict[str, Any]], names: dict[str, str]
) -> list[dict[str, Any]]:
    """Live comments, oldest first, as plain text – no other activity types."""
    result: list[dict[str, Any]] = []
    for activity in activities:
        if activity.get("type") != ACTIVITY_TYPE_COMMENT or activity.get("deactivated_at"):
            continue
        attachment = activity.get("attachment")
        content = attachment.get("content") if isinstance(attachment, dict) else None
        if not isinstance(content, str) or not content.strip():
            continue
        author_id = activity.get("author_id")
        result.append(
            {
                "id": str(activity.get("id") or ""),
                "author": names.get(str(author_id)) if author_id is not None else None,
                "content": content.strip()[:MAX_LENGTH],
                "created_at": _timestamp(activity.get("created_at")),
            }
        )
    result.sort(key=lambda c: c["created_at"] or "")
    return result[-MAX_COMMENTS:]
