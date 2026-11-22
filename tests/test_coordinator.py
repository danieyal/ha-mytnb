"""Tests for coordinator.py."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from mytnb.models import BillHistoryEntry, MeterReading

from custom_components.mytnb.coordinator import MyTNBDataUpdateCoordinator
from tests.conftest import (
    MockAccountUsage,
    MockCustomerAccount,
    _bill_history,
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
        if getattr(acc_no, "account_number", acc_no) == "bbb":
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
        if getattr(acc_no, "account_number", acc_no) == "bad":
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


# ── retry/backoff behavior at the coordinator layer ────────────────────────


async def test_coordinator_retries_transient_account_fetch_failure(
    hass: HomeAssistant,
) -> None:
    """A transient retryable error in the per-account fetch is retried.

    The integration's retry layer (mirroring python-mytnb's per-request retry)
    should give the per-account gather a bounded second chance with backoff
    rather than immediately failing the account. Backoff sleeps are stubbed so
    the test stays fast.
    """
    from mytnb.exceptions import APIError

    mock_client = create_mock_client()

    # The four per-account calls run concurrently in asyncio.gather; fail the
    # usage fetch once with a retryable APIError, then succeed.
    usage_calls = 0

    async def flaky_usage(acc_no):  # noqa: ANN001 - matches the client signature
        nonlocal usage_calls
        usage_calls += 1
        if usage_calls == 1:
            raise APIError("transient blip", retryable=True)
        return MockAccountUsage()

    mock_client.get_account_usage_smart = flaky_usage

    coordinator = _make_coordinator(hass)

    async def _no_sleep(_delay: float) -> None:
        return None

    with patch("custom_components.mytnb.retry.asyncio.sleep", _no_sleep):
        mock_client.get_customer_accounts = AsyncMock(
            return_value=[MockCustomerAccount()]
        )
        coordinator._client = mock_client
        data = await coordinator._async_update_data()

    # The retry recovered the account instead of dropping it; usage was
    # attempted more than once (the first attempt's transient failure retried).
    assert usage_calls == 2
    assert "220123456789" in data
    assert data["220123456789"]["usage"] is not None


async def test_coordinator_retries_transient_discovery_failure(
    hass: HomeAssistant,
) -> None:
    """A transient retryable error during account discovery is retried."""
    from mytnb.exceptions import APIError

    mock_client = create_mock_client()
    discover_calls = 0

    async def flaky_discover():
        nonlocal discover_calls
        discover_calls += 1
        if discover_calls == 1:
            raise APIError("transient blip", retryable=True)
        return [MockCustomerAccount()]

    mock_client.get_customer_accounts = flaky_discover

    coordinator = _make_coordinator(hass)
    coordinator._client = mock_client

    async def _no_sleep(_delay: float) -> None:
        return None

    with patch("custom_components.mytnb.retry.asyncio.sleep", _no_sleep):
        data = await coordinator._async_update_data()

    assert discover_calls == 2  # retried once after the transient blip
    assert "220123456789" in data


async def test_coordinator_non_retryable_api_error_is_not_retried(
    hass: HomeAssistant,
) -> None:
    """A non-retryable APIError surfaces immediately without consuming retries.

    Discovery raising a plain (non-retryable) APIError must behave exactly as
    before the retry layer was added: it propagates to UpdateFailed without
    any backoff sleeps.
    """
    from mytnb.exceptions import APIError

    mock_client = create_mock_client()
    mock_client.get_customer_accounts = AsyncMock(
        side_effect=APIError("permanent")
    )

    coordinator = _make_coordinator(hass)
    coordinator._get_client = AsyncMock(return_value=mock_client)

    async def _no_sleep(_delay: float) -> None:
        return None

    with (
        patch("custom_components.mytnb.retry.asyncio.sleep", _no_sleep),
        pytest.raises(UpdateFailed),
    ):
        await coordinator._async_update_data()

    # The error is permanent, so discovery was attempted only once.
    assert mock_client.get_customer_accounts.await_count == 1


async def test_coordinator_reads_meter_readings_once_per_bill(
    hass: HomeAssistant,
) -> None:
    """The bill PDF is only downloaded again when a new bill appears."""
    mock_client = create_mock_client()
    coordinator = _make_coordinator(hass)
    coordinator._client = mock_client

    first = await coordinator._async_update_data()
    coordinator.data = first
    second = await coordinator._async_update_data()

    mock_client.get_meter_readings.assert_awaited_once()
    account, billing_no = mock_client.get_meter_readings.await_args.args
    assert account.account_number == "220123456789"
    assert billing_no == "12345"
    readings = second["220123456789"]["meter_readings"]
    assert [r.current_reading for r in readings] == [10319, 81]
    assert second["220123456789"]["meter_readings_bill"].billing_no == "12345"

    new_bill = BillHistoryEntry(billing_no="12346", amount=90.0)
    mock_client.get_bill_history.return_value = [new_bill, *_bill_history()]
    await coordinator._async_update_data()

    assert mock_client.get_meter_readings.await_count == 2
    assert mock_client.get_meter_readings.await_args.args[1] == "12346"


async def test_coordinator_keeps_meter_readings_when_bill_fails(
    hass: HomeAssistant,
) -> None:
    """A failed bill download keeps the previous readings and the account."""
    mock_client = create_mock_client()
    coordinator = _make_coordinator(hass)
    coordinator._client = mock_client
    coordinator.data = await coordinator._async_update_data()

    mock_client.get_bill_history.return_value = [
        BillHistoryEntry(billing_no="12346", amount=90.0)
    ]
    mock_client.get_meter_readings.side_effect = RuntimeError("PDF unavailable")
    data = await coordinator._async_update_data()

    assert data["220123456789"]["usage"] is not None
    assert data["220123456789"]["meter_readings_bill"].billing_no == "12345"
    assert [r.current_reading for r in data["220123456789"]["meter_readings"]] == [
        10319,
        81,
    ]


async def test_coordinator_meter_readings_without_bills(
    hass: HomeAssistant,
) -> None:
    """An account without bills has no readings and downloads nothing."""
    mock_client = create_mock_client()
    mock_client.get_bill_history.return_value = []
    coordinator = _make_coordinator(hass)
    coordinator._client = mock_client

    data = await coordinator._async_update_data()

    mock_client.get_meter_readings.assert_not_awaited()
    assert data["220123456789"]["meter_readings"] == []
    assert data["220123456789"]["meter_readings_bill"] is None


async def test_coordinator_retries_unread_bill_daily(
    hass: HomeAssistant, freezer
) -> None:
    """A bill without readings keeps the previous ones and is retried daily."""
    mock_client = create_mock_client()
    coordinator = _make_coordinator(hass)
    coordinator._client = mock_client
    coordinator.data = await coordinator._async_update_data()

    # A new bill whose PDF isn't available yet (or can't be read).
    mock_client.get_bill_history.return_value = [
        BillHistoryEntry(billing_no="12346", amount=90.0)
    ]
    mock_client.get_meter_readings.return_value = []
    data = await coordinator._async_update_data()
    assert mock_client.get_meter_readings.await_count == 2
    assert data["220123456789"]["meter_readings_bill"].billing_no == "12345"
    assert len(data["220123456789"]["meter_readings"]) == 2

    # Hourly polls within the day don't download it again.
    freezer.tick(timedelta(hours=23))
    await coordinator._async_update_data()
    assert mock_client.get_meter_readings.await_count == 2

    # A day later it is tried again, and now has readings.
    freezer.tick(timedelta(hours=2))
    mock_client.get_meter_readings.return_value = [
        MeterReading(
            meter_number="SIE1052308047669",
            unit="kWh",
            previous_reading=10319,
            current_reading=10800,
            usage=481,
        )
    ]
    data = await coordinator._async_update_data()
    assert mock_client.get_meter_readings.await_count == 3
    assert data["220123456789"]["meter_readings_bill"].billing_no == "12346"
    assert data["220123456789"]["meter_readings"][0].current_reading == 10800
