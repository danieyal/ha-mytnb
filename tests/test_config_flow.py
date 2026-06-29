"""Tests for config_flow.py."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.mytnb.const import DOMAIN


async def _start_flow(hass: HomeAssistant):
    """Start the config flow and return the flow ID."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    return result["flow_id"]


async def test_show_form(hass: HomeAssistant) -> None:
    """Test that the config flow shows the user form."""
    await _start_flow(hass)


async def test_successful_login(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test a successful config flow."""
    flow_id = await _start_flow(hass)

    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "myTNB (test@example.com)"
    assert result["data"][CONF_EMAIL] == "test@example.com"
    assert result["data"][CONF_PASSWORD] == "testpassword"


async def test_duplicate_entry(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test duplicate config entry is aborted."""
    flow_id = await _start_flow(hass)

    await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "testpassword",
        },
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_auth_error(
    hass: HomeAssistant,
) -> None:
    """Test authentication error during config flow."""
    from mytnb.exceptions import AuthenticationError

    flow_id = await _start_flow(hass)

    with patch(
        "mytnb.MyTNBClient.login",
        side_effect=AuthenticationError("auth failed"),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow_id,
            {
                CONF_EMAIL: "test@example.com",
                CONF_PASSWORD: "wrong",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "auth"


async def test_geo_blocked_error(
    hass: HomeAssistant,
) -> None:
    """Test geo-blocked error during config flow."""
    from mytnb.exceptions import GeoBlockedError

    flow_id = await _start_flow(hass)

    with patch(
        "mytnb.MyTNBClient.login",
        side_effect=GeoBlockedError(),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow_id,
            {
                CONF_EMAIL: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "geo_blocked"


async def test_api_error(
    hass: HomeAssistant,
) -> None:
    """Test API error during config flow."""
    from mytnb.exceptions import APIError

    flow_id = await _start_flow(hass)

    with patch(
        "mytnb.MyTNBClient.login",
        side_effect=APIError("api failed"),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow_id,
            {
                CONF_EMAIL: "test@example.com",
                CONF_PASSWORD: "testpassword",
            },
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "api_error"
