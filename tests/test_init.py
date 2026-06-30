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
from custom_components.mytnb.const import CONF_ACCOUNT_NUMBER, CONF_ACCOUNTS, CONF_OWNER_NAME, DOMAIN
from tests.conftest import make_account_dict

_BASE_ENTRY = {
    "version": 2,
    "minor_version": 1,
    "domain": DOMAIN,
    "options": {},
    "source": "user",
    "discovery_keys": {},
    "unique_id": None,
    "subentries_data": (),
}

_BASE_ENTRY_DATA = {
    CONF_EMAIL: "test@example.com",
    CONF_PASSWORD: "testpassword",
    CONF_ACCOUNTS: [make_account_dict()],
}


async def test_setup_entry(hass: HomeAssistant, mock_mytnb_client) -> None:
    """Test setting up a config entry."""
    entry = ConfigEntry(
        **_BASE_ENTRY,
        title="myTNB (test@example.com)",
        data=_BASE_ENTRY_DATA,
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
        data=_BASE_ENTRY_DATA,
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
        data=_BASE_ENTRY_DATA,
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


async def test_migrate_entry_v1_to_v2(hass: HomeAssistant) -> None:
    """Test migrating from version 1 to version 2."""
    v1_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="myTNB",
        data={
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        options={},
        source="user",
        discovery_keys={},
        unique_id=None,
        entry_id="test_migrate",
        subentries_data=(),
    )
    # Register the entry so async_update_entry works
    hass.config_entries._entries[v1_entry.entry_id] = v1_entry

    with patch(
        "custom_components.mytnb._validate_login",
        AsyncMock(
            return_value=[
                {CONF_ACCOUNT_NUMBER: "111111111111", CONF_OWNER_NAME: "Alice"},
                {CONF_ACCOUNT_NUMBER: "222222222222", CONF_OWNER_NAME: "Bob"},
            ]
        ),
    ):
        result = await async_migrate_entry(hass, v1_entry)

    assert result is True
    assert v1_entry.version == 2
    assert len(v1_entry.data[CONF_ACCOUNTS]) == 2
    assert v1_entry.data[CONF_ACCOUNTS][0][CONF_ACCOUNT_NUMBER] == "111111111111"


async def test_migrate_entry_v1_failed(hass: HomeAssistant) -> None:
    """Test v1 migration fails gracefully on API error."""
    v1_entry = ConfigEntry(
        version=1,
        minor_version=1,
        domain=DOMAIN,
        title="myTNB",
        data={
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
        options={},
        source="user",
        discovery_keys={},
        unique_id=None,
        entry_id="test",
        subentries_data=(),
    )

    with patch(
        "custom_components.mytnb._validate_login",
        AsyncMock(side_effect=RuntimeError("API down")),
    ):
        result = await async_migrate_entry(hass, v1_entry)

    assert result is False
    assert v1_entry.version == 1  # unchanged


async def test_migrate_entry_unknown(hass: HomeAssistant) -> None:
    """Test migration from unknown version returns False."""
    entry_kwargs = dict(
        version=99,
        minor_version=1,
        domain=DOMAIN,
        data={},
        title="myTNB",
        options={},
        source="user",
        discovery_keys={},
        unique_id=None,
        entry_id="test",
        subentries_data=(),
    )
    entry = ConfigEntry(**entry_kwargs)
    result = await async_migrate_entry(hass, entry)
    assert result is False
