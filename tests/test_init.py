"""Tests for __init__.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from custom_components.mytnb import (
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.mytnb.const import DOMAIN

_BASE_ENTRY = {
    "version": 1,
    "minor_version": 1,
    "domain": DOMAIN,
    "options": {},
    "source": "user",
    "discovery_keys": {},
    "unique_id": None,
    "subentries_data": (),
}


async def test_setup_entry(hass: HomeAssistant, mock_mytnb_client) -> None:
    """Test setting up a config entry."""
    entry = ConfigEntry(
        **_BASE_ENTRY,
        title="myTNB (test@example.com)",
        data={
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        entry_id="test_entry_id",
    )

    with (
        patch(
            "custom_components.mytnb.MyTNBDataUpdateCoordinator",
            return_value=MagicMock(
                async_config_entry_first_refresh=AsyncMock(),
                async_add_listener=MagicMock(),
                data={"220123456789": {}},
                _client=None,
            ),
        ),
        patch.object(
            hass.config_entries,
            "async_forward_entry_setups",
            AsyncMock(),
        ),
    ):
        result = await async_setup_entry(hass, entry)

    assert result is True
    assert DOMAIN in hass.data
    assert "test_entry_id" in hass.data[DOMAIN]


async def test_unload_entry(hass: HomeAssistant) -> None:
    """Test unloading a config entry."""
    mock_coordinator = MagicMock()
    mock_coordinator._client = MagicMock()
    mock_coordinator._client.aclose = AsyncMock()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["test_entry_id"] = mock_coordinator

    entry = ConfigEntry(
        **_BASE_ENTRY,
        title="myTNB",
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "pw"},
        entry_id="test_entry_id",
    )
    entry.runtime_data = mock_coordinator

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is True
    assert "test_entry_id" not in hass.data[DOMAIN]
    mock_coordinator._client.aclose.assert_called_once()


async def test_unload_entry_platform_failure(hass: HomeAssistant) -> None:
    """Test unloading when platform unload fails."""
    mock_coordinator = MagicMock()
    mock_coordinator._client = None
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN]["test_entry_id"] = mock_coordinator

    entry = ConfigEntry(
        **_BASE_ENTRY,
        title="myTNB",
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "pw"},
        entry_id="test_entry_id",
    )
    entry.runtime_data = mock_coordinator

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=False),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is False
    assert "test_entry_id" in hass.data[DOMAIN]


async def test_migrate_entry_v1(hass: HomeAssistant) -> None:
    """Test migrating from version 1 (current version)."""
    entry = ConfigEntry(
        **_BASE_ENTRY,
        title="myTNB",
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "pw"},
        entry_id="test",
    )
    result = await async_migrate_entry(hass, entry)
    assert result is True


async def test_migrate_entry_unknown(hass: HomeAssistant) -> None:
    """Test migration from unknown version returns False."""
    entry_kwargs = dict(_BASE_ENTRY)
    entry_kwargs.update(
        version=99,
        data={},
        title="myTNB",
        entry_id="test",
    )
    entry = ConfigEntry(**entry_kwargs)
    result = await async_migrate_entry(hass, entry)
    assert result is False
