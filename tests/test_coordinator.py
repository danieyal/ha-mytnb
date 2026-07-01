"""Tests for coordinator.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.mytnb.coordinator import MyTNBDataUpdateCoordinator
from tests.conftest import (
    MockAccountUsage,
    MockCustomerAccount,
    create_mock_client,
    make_account_dict,
)


@pytest.fixture(autouse=True)
def _patch_frame_report():
    """Suppress ContextVar checks for tests that don't use real config entries."""
    with patch("homeassistant.helpers.frame.report_usage"):
        yield


def _make_coordinator(
    hass,
    email="test@example.com",
    password="testpassword",
    accounts=None,
):
    """Create a coordinator with default accounts."""
    if accounts is None:
        accounts = [make_account_dict()]
    return MyTNBDataUpdateCoordinator(hass, email, password, accounts)


async def test_coordinator_first_refresh(
    hass: HomeAssistant,
    mock_mytnb_client,
) -> None:
    """Test coordinator fetches data on first refresh."""
    coordinator = _make_coordinator(hass)
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
    """Test coordinator handles multiple configured accounts."""
    accounts = [
        make_account_dict("111111111111"),
        make_account_dict("222222222222"),
    ]

    mock_client = create_mock_client()
    mock_client.get_customer_accounts = AsyncMock(
        return_value=[
            MockCustomerAccount(account_number="111111111111"),
            MockCustomerAccount(account_number="222222222222"),
        ]
    )

    coordinator = _make_coordinator(hass, accounts=accounts)
    coordinator._client = mock_client

    data = await coordinator._async_update_data()

    assert "111111111111" in data
    assert "222222222222" in data


async def test_coordinator_login_on_first_use(
    hass: HomeAssistant,
) -> None:
    """Test coordinator performs login when _client is None."""
    mock_client = create_mock_client()

    coordinator = _make_coordinator(hass)
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
    """Test coordinator re-logins once when the session has expired."""
    from mytnb.exceptions import AuthenticationError

    mock_client1 = create_mock_client()
    mock_client1.get_customer_accounts = AsyncMock(
        side_effect=AuthenticationError("session expired")
    )
    mock_client2 = create_mock_client()

    coordinator = _make_coordinator(hass)
    coordinator._client = mock_client1

    import mytnb

    original = mytnb.MyTNBClient.login
    mytnb.MyTNBClient.login = AsyncMock(return_value=mock_client2)

    try:
        accounts = await coordinator._discover_accounts()
        # Re-login swapped in the fresh client and its discovery succeeded.
        assert coordinator._client is mock_client2
        assert accounts == [MockCustomerAccount()]
    finally:
        mytnb.MyTNBClient.login = original


async def test_coordinator_auth_failure_raises_config_entry_auth_failed(
    hass: HomeAssistant,
) -> None:
    """A persistent auth failure surfaces as ConfigEntryAuthFailed."""
    from homeassistant.exceptions import ConfigEntryAuthFailed
    from mytnb.exceptions import AuthenticationError

    mock_client = create_mock_client()
    mock_client.get_customer_accounts = AsyncMock(
        side_effect=AuthenticationError("session expired")
    )

    coordinator = _make_coordinator(hass)
    coordinator._client = mock_client

    import mytnb

    original = mytnb.MyTNBClient.login
    # Re-login also fails authentication.
    mytnb.MyTNBClient.login = AsyncMock(
        side_effect=AuthenticationError("bad credentials")
    )

    try:
        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()
    finally:
        mytnb.MyTNBClient.login = original


async def test_coordinator_total_failure_raises_update_failed(
    hass: HomeAssistant,
) -> None:
    """When every account fetch fails and there is no prior data, fail hard."""
    mock_client = create_mock_client()
    mock_client.get_account_usage_smart = AsyncMock(
        side_effect=RuntimeError("boom")
    )

    coordinator = _make_coordinator(hass)
    coordinator._client = mock_client

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_retains_stale_data_on_transient_failure(
    hass: HomeAssistant,
) -> None:
    """When one account blips but another succeeds, the blip keeps its value."""
    accounts = [
        make_account_dict("aaa"),
        make_account_dict("bbb"),
    ]
    mock_client = create_mock_client()
    mock_client.get_customer_accounts = AsyncMock(
        return_value=[
            MockCustomerAccount(account_number="aaa"),
            MockCustomerAccount(account_number="bbb"),
        ]
    )

    coordinator = _make_coordinator(hass, accounts=accounts)
    coordinator._client = mock_client

    # First cycle: both accounts succeed and populate data.
    first = await coordinator._async_update_data()
    assert "aaa" in first and "bbb" in first
    coordinator.data = first  # emulate DataUpdateCoordinator storing the result

    # Second cycle: usage fetch fails only for account "bbb".
    async def fail_for_bbb(acc_no):
        if acc_no == "bbb":
            raise RuntimeError("transient")
        return MockAccountUsage()

    mock_client.get_account_usage_smart = fail_for_bbb
    second = await coordinator._async_update_data()

    # "aaa" refreshes; "bbb" is retained with its previous value, not dropped.
    assert "aaa" in second
    assert "bbb" in second
    assert second["bbb"] == first["bbb"]


async def test_coordinator_partial_failure(
    hass: HomeAssistant,
) -> None:
    """Test coordinator continues when one account fetch fails."""
    accounts = [
        make_account_dict("good"),
        make_account_dict("bad"),
    ]

    mock_client = create_mock_client()
    mock_client.get_customer_accounts = AsyncMock(
        return_value=[
            MockCustomerAccount(account_number="good"),
            MockCustomerAccount(account_number="bad"),
        ]
    )

    async def fail_for_bad(acc_no):
        if acc_no == "bad":
            raise RuntimeError("Simulated failure")
        return MockAccountUsage()

    mock_client.get_account_usage_smart = fail_for_bad

    coordinator = _make_coordinator(hass, accounts=accounts)
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

    coordinator = _make_coordinator(hass)
    coordinator._get_client = AsyncMock(return_value=mock_client)

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

    coordinator = _make_coordinator(hass)
    coordinator._get_client = AsyncMock(return_value=mock_client)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_no_accounts(
    hass: HomeAssistant,
) -> None:
    """Test coordinator with no configured accounts returns empty dict."""
    coordinator = _make_coordinator(hass, accounts=[])

    data = await coordinator._async_update_data()

    assert data == {}


async def test_coordinator_account_numbers_property(
    hass: HomeAssistant,
) -> None:
    """Test the account_numbers property."""
    accounts = [
        make_account_dict("111"),
        make_account_dict("222"),
    ]
    coordinator = _make_coordinator(hass, accounts=accounts)

    assert coordinator.account_numbers == ["111", "222"]
