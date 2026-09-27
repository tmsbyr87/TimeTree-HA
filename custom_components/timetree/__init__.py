"""TimeTree calendar integration for Home Assistant.

Uses the unofficial TimeTree web endpoints (the public API was retired on
2023-12-22). Credentials are entered once in the config flow; the session
cookie is reused and renewed automatically.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN, STATIC_URL_BASE
from .coordinator import TimeTreeCoordinator

PLATFORMS: list[Platform] = [Platform.CALENDAR]
_BRAND_DIR = Path(__file__).parent / "brand"


async def _async_register_brand_assets(hass: HomeAssistant) -> None:
    """Serve brand/ from the integration folder (no www/ copy needed)."""
    if hass.data.get(f"{DOMAIN}_static_registered"):
        return
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_URL_BASE, str(_BRAND_DIR), cache_headers=True)]
    )
    hass.data[f"{DOMAIN}_static_registered"] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a TimeTree calendar from a config entry."""
    await _async_register_brand_assets(hass)
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
