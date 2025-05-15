"""The Teleco Daisy integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .hub import DaisyHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["light", "cover"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Teleco Daisy from a config entry."""
    daisy_hub = DaisyHub(
        hass,
        entry.data["username"],
        entry.data["password"],
    )

    if not await daisy_hub.login():
        return False

    # Store the hub for other components to access
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = daisy_hub

    # Fetch entities (lights, covers) from the API
    await daisy_hub.async_fetch_entities()

    # Use the recommended approach for setting up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
