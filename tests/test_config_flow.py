"""Tests for config_flow.py."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.mytnb.config_flow import MyTNBConfigFlow


async def test_show_form(hass: HomeAssistant) -> None:
    """Test that the config flow shows the user form."""
    flow = MyTNBConfigFlow()
    flow.hass = hass

    result = await flow.async_step_user()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_successful_login(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test a successful config flow."""
    flow = MyTNBConfigFlow()
    flow.hass = hass

    result = await flow.async_step_user(
        {
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "testpassword",
        }
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
    flow = MyTNBConfigFlow()
    flow.hass = hass
    flow._async_current_entries = lambda: [
        type("MockEntry", (), {"unique_id": "test@example.com"})(),
    ]

    result = await flow.async_step_user(
        {
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "testpassword",
        }
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_auth_error(
    hass: HomeAssistant,
) -> None:
    """Test authentication error during config flow."""
    from mytnb.exceptions import AuthenticationError

    with patch(
        "mytnb.MyTNBClient.login",
        side_effect=AuthenticationError("auth failed"),
    ):
        flow = MyTNBConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user(
            {
                CONF_EMAIL: "test@example.com",
                CONF_PASSWORD: "wrong",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "auth"


async def test_geo_blocked_error(
    hass: HomeAssistant,
) -> None:
    """Test geo-blocked error during config flow."""
    from mytnb.exceptions import GeoBlockedError

    with patch("mytnb.MyTNBClient.login", side_effect=GeoBlockedError("geo blocked")):
        flow = MyTNBConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user(
            {
                CONF_EMAIL: "test@example.com",
                CONF_PASSWORD: "testpassword",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "geo_blocked"


async def test_api_error(
    hass: HomeAssistant,
) -> None:
    """Test API error during config flow."""
    from mytnb.exceptions import APIError

    with patch("mytnb.MyTNBClient.login", side_effect=APIError("api failed")):
        flow = MyTNBConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user(
            {
                CONF_EMAIL: "test@example.com",
                CONF_PASSWORD: "testpassword",
            }
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"]["base"] == "api_error"
