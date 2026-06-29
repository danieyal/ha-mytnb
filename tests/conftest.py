"""Test fixtures for myTNB integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class MockTariffBlock:
    block: str = "Block 1"
    rate: float = 0.218
    usage: float = 200.0
    cost: float = 43.60


@dataclass
class MockBillingMonth:
    month: int = 6
    year: int = 2026
    usage_total: float = 450.0
    amount_total: float = 98.10
    tariff_blocks: list[MockTariffBlock] = field(
        default_factory=lambda: [MockTariffBlock()],
    )


@dataclass
class MockByMonth:
    months: list[MockBillingMonth] = field(
        default_factory=lambda: [MockBillingMonth()],
    )


@dataclass
class MockDailyUsage:
    date: date = date(2026, 6, 29)
    usage: float = 15.0
    cost: float = 3.27


@dataclass
class MockDaily:
    days: list[MockDailyUsage] = field(
        default_factory=lambda: [MockDailyUsage()],
    )


@dataclass
class MockMetrics:
    current_usage: float = 120.0
    average_usage: float = 14.5
    current_cost: float = 26.16
    projected_cost: float = 115.00


@dataclass
class MockAccountUsage:
    metrics: MockMetrics = field(default_factory=MockMetrics)
    by_month: MockByMonth = field(default_factory=MockByMonth)
    daily: MockDaily = field(default_factory=MockDaily)


@dataclass
class MockBillEntry:
    date: date = date(2026, 5, 15)
    amount: float = 87.50


@dataclass
class MockDueAmount:
    amount_due: float = 26.16


@dataclass
class MockCustomerAccount:
    account_number: str = "220123456789"
    owner_name: str = "Test Owner"
    address: str = "123 Test St, Kuala Lumpur"
    is_smart_meter: bool = True


def create_mock_account_data(
    account_number: str = "220123456789",
) -> dict[str, Any]:
    """Create a mock coordinator data entry for a single account."""
    return {
        account_number: {
            "account": MockCustomerAccount(account_number=account_number),
            "usage": MockAccountUsage(),
            "bill_history": [MockBillEntry()],
            "due": MockDueAmount(),
        }
    }


def create_mock_client() -> MagicMock:
    """Create a fully mocked MyTNBClient."""
    client = MagicMock()
    client.get_customer_accounts = AsyncMock(
        return_value=[MockCustomerAccount()],
    )
    client.get_account_usage_smart = AsyncMock(
        return_value=MockAccountUsage(),
    )
    client.get_bill_history = AsyncMock(
        return_value=[MockBillEntry()],
    )
    client.get_account_due_amount = AsyncMock(
        return_value=MockDueAmount(),
    )
    client.aclose = AsyncMock()
    return client


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations."""
    yield


@pytest.fixture
def mock_mytnb_client():
    """Provide a mocked MyTNBClient and patch the mytnb module."""
    mock_client = create_mock_client()

    with patch("mytnb.MyTNBClient") as mock_cls:
        mock_cls.login = AsyncMock(return_value=mock_client)
        yield mock_client


@pytest.fixture
def config_entry_data():
    """Default config entry data."""
    return {
        "email": "test@example.com",
        "password": "testpassword",
    }
