"""TimeTree calendar integration for Home Assistant.

Uses the unofficial TimeTree web endpoints (the public API was retired on
2023-12-22). Credentials are entered once in the config flow; the session
cookie is reused and renewed automatically.
"""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import voluptuous as vol

from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.loader import async_get_integration
from homeassistant.util import dt as dt_util

from .const import CARD_FILENAME, CARD_URL_BASE, DOMAIN, STATIC_URL_BASE
from .api import TimeTreeBusy, TimeTreeError
from .comments import UID_RE
from .coordinator import TimeTreeAccount, TimeTreeCoordinator, coordinator_for_entity
from .insights import describe, next_event
from .entry_data import account_unique_id, migrate_v1, selected_calendars
from .views import TimeTreeCommentsView, TimeTreeEventsView, TimeTreeLabelsView

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SERVICE_EVENT_DETAILS = "get_event_details"
SERVICE_EVENT_DETAILS_SCHEMA = vol.Schema(
    {vol.Required("entity_id"): cv.entity_id, vol.Optional("uid"): cv.string}
)

PLATFORMS: list[Platform] = [Platform.CALENDAR, Platform.SENSOR]
_BRAND_DIR = Path(__file__).parent / "brand"
_WWW_DIR = Path(__file__).parent / "www"
BLUEPRINT_FILENAME = "timetree_reminder.yaml"


async def _async_register_static_assets(hass: HomeAssistant) -> None:
    """Serve brand/ and www/ from the integration folder (no www/ copy needed)."""
    if hass.data.get(f"{DOMAIN}_static_registered"):
        return
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(STATIC_URL_BASE, str(_BRAND_DIR), cache_headers=True),
            StaticPathConfig(CARD_URL_BASE, str(_WWW_DIR), cache_headers=False),
        ]
    )
    # Label-aware event feed for the bundled card (authenticated).
    hass.http.register_view(TimeTreeEventsView())
    hass.http.register_view(TimeTreeLabelsView())
    hass.http.register_view(TimeTreeCommentsView())
    hass.data[f"{DOMAIN}_static_registered"] = True


async def _async_register_card_resource(hass: HomeAssistant) -> None:
    """Add the bundled timetree-card to the Lovelace resources (storage mode).

    Users therefore get the card in the card picker right after install,
    without touching Settings → Dashboards → Resources. The URL carries the
    integration version so browsers pick up card updates.
    """
    if hass.data.get(f"{DOMAIN}_resource_registered"):
        return
    integration = await async_get_integration(hass, DOMAIN)
    url = f"{CARD_URL_BASE}/{CARD_FILENAME}?v={integration.version}"

    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None or getattr(lovelace, "mode", "storage") != "storage":
        _LOGGER.info(
            "Lovelace runs in YAML mode – add the TimeTree card resource manually: %s (type: module)",
            url,
        )
        return
    if not resources.loaded:
        await resources.async_load()

    existing = [
        item for item in resources.async_items()
        if str(item.get("url", "")).startswith(f"{CARD_URL_BASE}/{CARD_FILENAME}")
    ]
    if existing:
        current = existing[0]
        if current.get("url") != url:
            await resources.async_update_item(current["id"], {"res_type": "module", "url": url})
            _LOGGER.debug("Updated TimeTree card resource to %s", url)
        for stale in existing[1:]:
            await resources.async_delete_item(stale["id"])
    else:
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Registered TimeTree card resource %s", url)
    hass.data[f"{DOMAIN}_resource_registered"] = True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the integration-wide actions."""

    async def _event_details(call: ServiceCall) -> ServiceResponse:
        coordinator = coordinator_for_entity(hass, call.data["entity_id"])
        if coordinator is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_a_timetree_calendar"
            )
        store = coordinator.data
        uid = call.data.get("uid")
        if uid is None:
            item = next_event(store.window, dt_util.now())
            if item is None:
                return {"event": None, "comments": [], "media": []}
            uid = item.uid
        if not UID_RE.match(uid) or not store.has(uid):
            raise ServiceValidationError(translation_domain=DOMAIN, translation_key="unknown_event")
        try:
            activity = await coordinator.async_get_activity(uid)
        except TimeTreeBusy as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="busy") from err
        except TimeTreeError as err:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="unavailable") from err
        occurrence = next((i for i in store.window if i.uid == uid), None)
        tz = dt_util.get_default_time_zone()
        return {
            "event": (
                describe(occurrence, tz, store.label_of(uid)) if occurrence else {"uid": uid}
            )
            | {"media_count": store.media_count_of(uid)},
            "comments": activity["comments"],
            "media": activity["media"],
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_EVENT_DETAILS,
        _event_details,
        schema=SERVICE_EVENT_DETAILS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """v1 (one entry per calendar) → v2 (one entry per account)."""
    if entry.version > 2:
        return False  # downgrade from a future version
    if entry.version == 1:
        data, options = migrate_v1(dict(entry.data), dict(entry.options))
        unique_id = account_unique_id(data.get("email", ""))
        # Two v1 entries of the same account cannot share the account id;
        # the second one simply keeps its old id and keeps working.
        taken = any(
            other.unique_id == unique_id
            for other in hass.config_entries.async_entries(DOMAIN)
            if other.entry_id != entry.entry_id
        )
        hass.config_entries.async_update_entry(
            entry,
            data=data,
            options=options,
            unique_id=entry.unique_id if taken or not unique_id else unique_id,
            version=2,
            minor_version=1,
        )
        _LOGGER.info("Migrated TimeTree entry %s to the account layout", entry.title)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a TimeTree account with its selected calendars."""
    await _async_register_static_assets(hass)
    try:
        await _async_register_card_resource(hass)
    except Exception:  # noqa: BLE001 – the card is a bonus, never block the calendar
        _LOGGER.exception("Could not register the TimeTree card resource")

    account = TimeTreeAccount(hass, entry)
    calendars = selected_calendars(dict(entry.data), dict(entry.options))
    # Sequential on purpose: if the stored session died, the first calendar
    # renews it and the others reuse the new cookie.
    for calendar_id, name in calendars.items():
        coordinator = TimeTreeCoordinator(hass, entry, account, calendar_id, name)
        await coordinator.async_config_entry_first_refresh()
        account.coordinators[calendar_id] = coordinator

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = account
    account.async_start_clock()
    await _async_install_blueprint(hass)
    _async_remove_unselected_devices(hass, entry, set(calendars))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def _async_install_blueprint(hass: HomeAssistant) -> None:
    """Copy the reminder blueprint to /config/blueprints once (never overwrite).

    Users may edit their copy; an existing file is left alone.
    """
    source = Path(__file__).parent / "blueprints" / BLUEPRINT_FILENAME
    target = Path(hass.config.path("blueprints", "automation", DOMAIN, BLUEPRINT_FILENAME))

    def _copy() -> bool:
        if target.exists() or not source.exists():
            return False
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        return True

    try:
        if await hass.async_add_executor_job(_copy):
            _LOGGER.info("Installed blueprint %s", target)
    except OSError as err:
        _LOGGER.warning("Could not install the TimeTree reminder blueprint: %s", err)


def _calendar_id_of(device: DeviceEntry) -> str | None:
    return next((ident for domain, ident in device.identifiers if domain == DOMAIN), None)


def _async_remove_unselected_devices(
    hass: HomeAssistant, entry: ConfigEntry, selected: set[int]
) -> None:
    """Drop devices (and with them entities) of calendars no longer synced."""
    keep = {str(c) for c in selected}
    registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        calendar_id = _calendar_id_of(device)
        if calendar_id is not None and calendar_id not in keep:
            registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> bool:
    """Allow deleting a calendar device only once it is deselected in the options."""
    account: TimeTreeAccount | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    calendar_id = _calendar_id_of(device)
    if account is None or calendar_id is None:
        return True
    return int(calendar_id) not in account.coordinators


async def _async_entry_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload on option changes – not on the session renewals stored in data."""
    account: TimeTreeAccount | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if account is not None and dict(entry.options) == account.options_snapshot:
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
