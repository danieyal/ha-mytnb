"""Tests for coordinator.py."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.mytnb.coordinator import MyTNBDataUpdateCoordinator
from tests.conftest import (
    MockAccountUsage,
    MockCustomerAccount,
    create_mock_client,
)


async def test_coordinator_first_refresh(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test coordinator fetches data on first refresh."""
    coordinator = MyTNBDataUpdateCoordinator(
        hass, "test@example.com", "testpassword"
    )
    coordinator._client = mock_mytnb_client

    data = await coordinator._async_update_data()

    assert "220123456789" in data
    assert data["220123456789"]["account"].account_number == "220123456789"
    assert data["220123456789"]["usage"] is not None
    assert len(data["220123456789"]["bill_history"]) == 1
    assert data["220123456789"]["due"] is not None


async def test_coordinator_multiple_accounts(
    hass: HomeAssistant,
) -> None:
    """Test coordinator handles multiple accounts."""
    accounts = [
        MockCustomerAccount(account_number="111111111111"),
        MockCustomerAccount(account_number="222222222222"),
    ]

    mock_client = create_mock_client()
    mock_client.get_customer_accounts = AsyncMock(return_value=accounts)

    coordinator = MyTNBDataUpdateCoordinator(
        hass, "test@example.com", "testpassword"
    )
    coordinator._client = mock_client

    data = await coordinator._async_update_data()

    assert "111111111111" in data
    assert "222222222222" in data


async def test_coordinator_login_on_first_use(
    hass: HomeAssistant,
) -> None:
    """Test coordinator performs login when _client is None."""
    mock_client = create_mock_client()

    coordinator = MyTNBDataUpdateCoordinator(
        hass, "test@example.com", "testpassword"
    )
    coordinator._client = None

    import mytnb

    original = mytnb.MyTNBClient.login
    mytnb.MyTNBClient.login = AsyncMock(return_value=mock_client)

    try:
        client = await coordinator._get_client()
        assert client is mock_client
    finally:
        mytnb.MyTNBClient.login = original


async def test_coordinator_relogin_on_auth_error(
    hass: HomeAssistant,
) -> None:
    """Test coordinator re-logins when session expires."""
    from mytnb.exceptions import AuthenticationError

    mock_client1 = create_mock_client()
    mock_client1.get_customer_accounts = AsyncMock(
        side_effect=AuthenticationError("session expired")
    )
    mock_client2 = create_mock_client()

    coordinator = MyTNBDataUpdateCoordinator(
        hass, "test@example.com", "testpassword"
    )
    coordinator._client = mock_client1

    import mytnb

    original = mytnb.MyTNBClient.login
    mytnb.MyTNBClient.login = AsyncMock(return_value=mock_client2)

    try:
        client = await coordinator._get_client()
        assert client is mock_client2
    finally:
        mytnb.MyTNBClient.login = original


async def test_coordinator_partial_failure(
    hass: HomeAssistant,
) -> None:
    """Test coordinator continues when one account fetch fails."""
    accounts = [
        MockCustomerAccount(account_number="good"),
        MockCustomerAccount(account_number="bad"),
    ]

    mock_client = create_mock_client()
    mock_client.get_customer_accounts = AsyncMock(return_value=accounts)

    async def fail_for_bad(acc_no):
        if acc_no == "bad":
            raise RuntimeError("Simulated failure")
        return MockAccountUsage()

    mock_client.get_account_usage_smart = fail_for_bad

    coordinator = MyTNBDataUpdateCoordinator(
        hass, "test@example.com", "testpassword"
    )
    coordinator._client = mock_client

    data = await coordinator._async_update_data()

    assert "good" in data
    assert "bad" not in data


async def test_coordinator_generic_error_raises_update_failed(
    hass: HomeAssistant,
) -> None:
    """Test generic error raises UpdateFailed."""
    mock_client = create_mock_client()
    mock_client.get_customer_accounts = AsyncMock(
        side_effect=RuntimeError("unexpected")
    )

    coordinator = MyTNBDataUpdateCoordinator(
        hass, "test@example.com", "testpassword"
    )
    coordinator._client = mock_client

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_api_error_raises_update_failed(
    hass: HomeAssistant,
) -> None:
    """Test API error raises UpdateFailed."""
    from mytnb.exceptions import APIError

    mock_client = create_mock_client()
    mock_client.get_customer_accounts = AsyncMock(
        side_effect=APIError("api failed")
    )

    coordinator = MyTNBDataUpdateCoordinator(
        hass, "test@example.com", "testpassword"
    )
    coordinator._client = mock_client

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
