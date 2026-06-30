"""Tests for config_flow.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.mytnb.const import (
    CONF_ACCOUNT_NUMBER,
    CONF_ACCOUNTS,
    CONF_OWNER_NAME,
    DOMAIN,
)
from tests.conftest import MockCustomerAccount


async def _start_flow(hass: HomeAssistant):
    """Start the config flow and return the flow ID."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    return result["flow_id"]


async def _complete_user_step(
    hass: HomeAssistant,
    flow_id: str,
    email: str = "test@example.com",
    password: str = "testpassword",
):
    """Complete the user step (credentials) and return result."""
    return await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_EMAIL: email,
            CONF_PASSWORD: password,
        },
    )


async def test_show_form(hass: HomeAssistant) -> None:
    """Test that the config flow shows the user form."""
    await _start_flow(hass)


async def test_successful_login_shows_accounts(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test that successful login advances to account selection step."""
    flow_id = await _start_flow(hass)

    result = await _complete_user_step(hass, flow_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "accounts"


async def test_full_flow_create_entry(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test complete flow: login → select accounts → create entry."""
    flow_id = await _start_flow(hass)

    # Step 1: credentials
    result = await _complete_user_step(hass, flow_id)
    assert result["step_id"] == "accounts"

    # Step 2: select accounts
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ACCOUNTS: ["220123456789"]},
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "myTNB (test@example.com)"
    assert result["data"][CONF_EMAIL] == "test@example.com"
    assert result["data"][CONF_PASSWORD] == "testpassword"
    assert len(result["data"][CONF_ACCOUNTS]) == 1
    assert result["data"][CONF_ACCOUNTS][0][CONF_ACCOUNT_NUMBER] == "220123456789"


async def test_account_step_no_selection(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test that not selecting any account shows an error."""
    flow_id = await _start_flow(hass)

    # Step 1: credentials
    await _complete_user_step(hass, flow_id)

    # Step 2: submit empty selection
    result = await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ACCOUNTS: []},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "accounts"
    assert result["errors"] == {CONF_ACCOUNTS: "select_at_least_one"}


async def test_duplicate_entry(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test duplicate config entry is aborted."""
    # Create the first entry
    flow_id = await _start_flow(hass)
    await _complete_user_step(hass, flow_id)
    await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ACCOUNTS: ["220123456789"]},
    )

    # Start a second flow — should abort at user step
    flow_id2 = await _start_flow(hass)
    result = await _complete_user_step(hass, flow_id2)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_no_accounts_after_login(
    hass: HomeAssistant,
) -> None:
    """Test error when login succeeds but no accounts found."""
    from mytnb import MyTNBClient

    mock_client = AsyncMock()
    mock_client.get_customer_accounts = AsyncMock(return_value=[])

    flow_id = await _start_flow(hass)

    with patch.object(MyTNBClient, "login", AsyncMock(return_value=mock_client)):
        result = await _complete_user_step(hass, flow_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "no_accounts"}


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
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "auth"}


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
    assert result["errors"] == {"base": "geo_blocked"}


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
    assert result["errors"] == {"base": "api_error"}


async def test_multiple_accounts_flow(
    hass: HomeAssistant,
) -> None:
    """Test flow with multiple discovered accounts."""
    accounts = [
        MockCustomerAccount(account_number="111111111111", owner_name="Alice"),
        MockCustomerAccount(account_number="222222222222", owner_name="Bob"),
    ]

    mock_client = AsyncMock()
    mock_client.get_customer_accounts = AsyncMock(return_value=accounts)

    flow_id = await _start_flow(hass)

    with patch(
        "custom_components.mytnb.config_flow.mytnb.MyTNBClient.login",
        AsyncMock(return_value=mock_client),
    ):
        # Step 1: credentials
        result = await _complete_user_step(hass, flow_id)
        assert result["step_id"] == "accounts"

        # Step 2: select only Alice's account
        result = await hass.config_entries.flow.async_configure(
            flow_id,
            {CONF_ACCOUNTS: ["111111111111"]},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert len(result["data"][CONF_ACCOUNTS]) == 1
    assert result["data"][CONF_ACCOUNTS][0][CONF_ACCOUNT_NUMBER] == "111111111111"
    assert result["data"][CONF_ACCOUNTS][0][CONF_OWNER_NAME] == "Alice"


# ── Options Flow Tests ──────────────────────────────────────────────


async def _create_entry_for_options(hass: HomeAssistant, mock_mytnb_client):
    """Create a config entry and return it for options flow testing."""
    flow_id = await _start_flow(hass)
    await _complete_user_step(hass, flow_id)
    await hass.config_entries.flow.async_configure(
        flow_id,
        {CONF_ACCOUNTS: ["220123456789"]},
    )
    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    return entries[0]


async def test_options_flow_show_form(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test options flow shows form with preselected accounts."""
    entry = await _create_entry_for_options(hass, mock_mytnb_client)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"


async def test_options_flow_no_selection(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test options flow errors when no accounts selected."""
    entry = await _create_entry_for_options(hass, mock_mytnb_client)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_ACCOUNTS: []},
    )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {CONF_ACCOUNTS: "select_at_least_one"}


async def test_options_flow_update_accounts(
    hass: HomeAssistant,
) -> None:
    """Test options flow updates selected accounts."""
    # Create accounts
    accounts = [
        MockCustomerAccount(account_number="111111111111", owner_name="Alice"),
        MockCustomerAccount(account_number="222222222222", owner_name="Bob"),
    ]
    mock_client = AsyncMock()
    mock_client.get_customer_accounts = AsyncMock(return_value=accounts)

    with patch(
        "custom_components.mytnb.config_flow.mytnb.MyTNBClient.login",
        AsyncMock(return_value=mock_client),
    ):
        # Create entry with only Alice
        flow_id = await _start_flow(hass)
        await _complete_user_step(hass, flow_id)
        await hass.config_entries.flow.async_configure(
            flow_id,
            {CONF_ACCOUNTS: ["111111111111"]},
        )

    entries = hass.config_entries.async_entries(DOMAIN)
    entry = entries[0]

    # Now open options and add Bob too
    with patch(
        "custom_components.mytnb.config_flow.mytnb.MyTNBClient.login",
        AsyncMock(return_value=mock_client),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ACCOUNTS: ["111111111111", "222222222222"]},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    # Verify the entry data was updated
    updated_accounts = entry.data[CONF_ACCOUNTS]
    assert len(updated_accounts) == 2
    account_numbers = {acc[CONF_ACCOUNT_NUMBER] for acc in updated_accounts}
    assert account_numbers == {"111111111111", "222222222222"}
