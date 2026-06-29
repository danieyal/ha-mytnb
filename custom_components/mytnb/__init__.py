"""The myTNB integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import MyTNBDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

type MyTNBConfigEntry = ConfigEntry[MyTNBDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MyTNBConfigEntry) -> bool:
    """Set up myTNB from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    coordinator = MyTNBDataUpdateCoordinator(hass, email, password)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyTNBConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = entry.runtime_data
        hass.data[DOMAIN].pop(entry.entry_id)
        if coordinator and coordinator._client:
            await coordinator._client.aclose()

    return unload_ok


async def async_update_listener(hass: HomeAssistant, entry: MyTNBConfigEntry) -> None:
    """Handle config entry options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry."""
    if entry.version == 1:
        return True
    _LOGGER.warning(
        "Migration from config entry version %s is not supported", entry.version
    )
    return False
