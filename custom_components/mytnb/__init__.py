"""The myTNB integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .config_flow import _validate_login
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_ACCOUNTS,
    CONF_OWNER_NAME,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MyTNBDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

type MyTNBConfigEntry = ConfigEntry[MyTNBDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MyTNBConfigEntry) -> bool:
    """Set up myTNB from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    accounts: list[dict[str, str]] = entry.data.get(CONF_ACCOUNTS, [])

    coordinator = MyTNBDataUpdateCoordinator(hass, email, password, accounts)
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
        # v1 → v2: auto-discover all accounts and store them in data
        email = entry.data[CONF_EMAIL]
        password = entry.data[CONF_PASSWORD]

        try:
            discovered = await _validate_login(email, password)
        except Exception as exc:
            _LOGGER.error("Migration failed for %s: %s", email, exc)
            return False

        accounts = [
            {
                CONF_ACCOUNT_NUMBER: acc[CONF_ACCOUNT_NUMBER],
                CONF_OWNER_NAME: acc[CONF_OWNER_NAME],
            }
            for acc in discovered
        ]

        hass.config_entries.async_update_entry(
            entry,
            data={
                CONF_EMAIL: email,
                CONF_PASSWORD: password,
                CONF_ACCOUNTS: accounts,
            },
            version=2,
        )
        _LOGGER.info(
            "Migrated entry for %s to v2 with %d accounts",
            email,
            len(accounts),
        )
        return True

    _LOGGER.warning(
        "Migration from config entry version %s is not supported", entry.version
    )
    return False
