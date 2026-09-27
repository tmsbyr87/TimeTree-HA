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
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import CARD_FILENAME, CARD_URL_BASE, DOMAIN, STATIC_URL_BASE
from .coordinator import TimeTreeCoordinator
from .views import TimeTreeEventsView, TimeTreeLabelsView

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CALENDAR]
_BRAND_DIR = Path(__file__).parent / "brand"
_WWW_DIR = Path(__file__).parent / "www"


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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a TimeTree calendar from a config entry."""
    await _async_register_static_assets(hass)
    try:
        await _async_register_card_resource(hass)
    except Exception:  # noqa: BLE001 – the card is a bonus, never block the calendar
        _LOGGER.exception("Could not register the TimeTree card resource")
    coordinator = TimeTreeCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when the polling interval changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
