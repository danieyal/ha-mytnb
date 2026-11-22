"""The myTNB integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .config_flow import _validate_login
from .const import (
    CONF_ACCOUNT_NUMBER,
    CONF_ACCOUNTS,
    CONF_OWNER_NAME,
    DOMAIN,
    MONETARY_SENSOR_KEYS,
    PLATFORMS,
)
from .coordinator import MyTNBDataUpdateCoordinator
from .statistics import async_relabel_currency, daily_statistic_id

_LOGGER = logging.getLogger(__name__)

type MyTNBConfigEntry = ConfigEntry[MyTNBDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MyTNBConfigEntry) -> bool:
    """Set up myTNB from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    accounts: list[dict[str, str]] = entry.data.get(CONF_ACCOUNTS, [])

    await _async_relabel_currency(hass, entry)

    coordinator = MyTNBDataUpdateCoordinator(hass, email, password, accounts)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MyTNBConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator = entry.runtime_data
        if coordinator and coordinator._client:
            await coordinator._client.close()

    return unload_ok


async def async_update_listener(hass: HomeAssistant, entry: MyTNBConfigEntry) -> None:
    """Handle config entry options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entry."""
    if entry.version > 2:
        _LOGGER.warning(
            "Migration from config entry version %s is not supported", entry.version
        )
        return False

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


async def _async_relabel_currency(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Relabel the stored RM statistics of this entry's accounts as MYR.

    Versions before 1.5.0 reported money in RM. This runs on every setup,
    before the sensors report MYR, so it also covers an account that is
    selected again later. The recorder then keeps compiling their statistics
    instead of stopping at the unit change. A failure only means the user gets
    the recorder's own repair for the affected sensors, so it must not stop
    the entry from loading.
    """
    if "recorder" not in hass.config.components:
        return
    registry = er.async_get(hass)
    statistic_ids: set[str] = set()
    for account in entry.data.get(CONF_ACCOUNTS, []):
        number = account[CONF_ACCOUNT_NUMBER]
        statistic_ids.add(daily_statistic_id(number, "cost"))
        for key in MONETARY_SENSOR_KEYS:
            entity_id = registry.async_get_entity_id(
                Platform.SENSOR, DOMAIN, f"{DOMAIN}_{number}_{key}"
            )
            if entity_id:
                statistic_ids.add(entity_id)
    try:
        await async_relabel_currency(hass, statistic_ids)
    except Exception:  # noqa: BLE001 - see docstring
        _LOGGER.warning(
            "Could not relabel myTNB statistics from RM to MYR; Home Assistant "
            "will offer to fix them under Settings > Repairs",
            exc_info=True,
        )
