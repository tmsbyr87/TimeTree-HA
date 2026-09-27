"""Constants for the TimeTree integration."""

from __future__ import annotations

DOMAIN = "timetree"

# Brand assets are served by the integration itself from its brand/ folder.
STATIC_URL_BASE = "/timetree_static"
# The bundled Lovelace card lives in www/ and is served under this base.
CARD_URL_BASE = "/timetree_card"
CARD_FILENAME = "timetree-card.js"

API_BASE_URL = "https://timetreeapp.com/api/v1"
API_V2_BASE_URL = "https://timetreeapp.com/api/v2"
API_USER_AGENT = "web/2.1.0/en"
SESSION_COOKIE = "_session_id"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_SESSION_ID = "session_id"
# Config entry v1 stored exactly one calendar; kept for the v1 → v2 migration.
CONF_CALENDAR_ID = "calendar_id"
CONF_CALENDAR_NAME = "calendar_name"
# Config entry v2: one entry per TimeTree account.
#   data["calendar_names"]  {"<calendar id>": "<name>"} – names last seen
#   options["calendars"]    ["<calendar id>", ...]      – calendars to sync
CONF_CALENDAR_NAMES = "calendar_names"
CONF_CALENDARS = "calendars"
CONF_SCAN_INTERVAL = "scan_interval"

# Fired on the event bus when a TimeTree alert ("remind me 15 min before")
# becomes due. See blueprints/timetree_reminder.yaml.
EVENT_REMINDER = "timetree_reminder"

DEFAULT_SCAN_INTERVAL_MINUTES = 15
MIN_SCAN_INTERVAL_MINUTES = 5
MAX_SCAN_INTERVAL_MINUTES = 120

# TimeTree event classification (see reference project eoleedi/TimeTree-Exporter)
EVENT_TYPE_NORMAL = 0
EVENT_TYPE_BIRTHDAY = 1
EVENT_CATEGORY_NORMAL = 1
EVENT_CATEGORY_MEMO = 2

# TimeTree API error codes returned in the login response body
API_ERROR_INVALID_CREDENTIALS = -702
API_ERROR_RATE_LIMITED = -495
