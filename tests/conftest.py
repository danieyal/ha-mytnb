"""Test fixtures for myTNB integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Mock models matching python-mytnb Pydantic shapes ────────────────


@dataclass
class MockTariffBlock:
    """Matches mytnb.models.MonthlyTariffBlock."""
    block_id: str = "Block 1"
    block_pricing: str = "0.218"
    usage: float = 200.0
    amount: float = 43.60


@dataclass
class MockBillingMonth:
    """Matches mytnb.models.BillingMonth."""
    month: int = 6
    year: int = 2026
    usage_total: str = "450.0"
    amount_total: str = "98.10"
    tariff_blocks: list[MockTariffBlock] = field(
        default_factory=lambda: [MockTariffBlock()],
    )

    @property
    def usage_kwh(self) -> float:
        return float(self.usage_total)

    @property
    def amount_rm(self) -> float:
        return float(self.amount_total)


@dataclass
class MockByMonth:
    """Matches mytnb.models.ByMonthData."""
    months: list[MockBillingMonth] = field(
        default_factory=lambda: [MockBillingMonth()],
    )


@dataclass
class MockDailyUsage:
    """Matches mytnb.models.DailyUsage."""
    date: str = "2026-06-29"
    consumption: str = "15.0"
    amount: str = "3.27"

    @property
    def consumption_kwh(self) -> float:
        return float(self.consumption)

    @property
    def amount_rm(self) -> float:
        return float(self.amount)


@dataclass
class MockDailyUsageWeek:
    """Matches mytnb.models.DailyUsageWeek."""
    days: list[MockDailyUsage] = field(
        default_factory=lambda: [MockDailyUsage()],
    )


@dataclass
class MockAccountUsage:
    """Matches mytnb.models.AccountUsage."""
    current_usage_kwh: float = 120.0
    average_usage_kwh: float = 14.5
    current_cost_rm: float = 26.16
    projected_cost_rm: float = 115.00
    by_month: MockByMonth = field(default_factory=MockByMonth)
    by_day: list[MockDailyUsageWeek] = field(
        default_factory=lambda: [MockDailyUsageWeek()],
    )


# ── Raw API shapes (what the python-mytnb client returns) ────────────


def _raw_due_amount(amount_due: str = "26.16", due_date: str = "2026-06-30") -> dict:
    """Raw API shape for get_account_due_amount()."""
    return {"AccountAmountDue": {"amountDue": amount_due, "billDueDate": due_date}}


def _raw_bill_history(amount: str = "87.50", date_str: str = "2026-05-15") -> list[dict]:
    """Raw API shape for get_bill_history()."""
    return [{"DtBill": date_str, "AmPayable": amount, "BillingNo": "12345"}]


# ── Normalized shapes (what the coordinator stores) ──────────────────


def _norm_due(amount_due: float = 26.16, due_date: str = "2026-06-30") -> dict:
    """Normalized due amount after coordinator normalization."""
    return {"amount_due": amount_due, "due_date": due_date}


def _norm_bill_entry(amount: float = 87.50, date_str: str = "2026-05-15") -> dict:
    """Normalized bill history entry after coordinator normalization."""
    return {"date": date_str, "amount": amount}


# ── Mock CustomerAccount ─────────────────────────────────────────────


@dataclass
class MockCustomerAccount:
    """Matches mytnb.models.CustomerAccount."""
    account_number: str = "220123456789"
    owner_name: str = "Test Owner"
    account_st_address: str = "123 Test St, Kuala Lumpur"
    is_smart_meter: bool = True

    @property
    def address(self) -> str:
        """Alias for sensor extra_state_attributes compatibility."""
        return self.account_st_address


def create_mock_account_data(
    account_number: str = "220123456789",
) -> dict[str, Any]:
    """Create a mock coordinator data entry (normalized shape)."""
    return {
        account_number: {
            "account": MockCustomerAccount(account_number=account_number),
            "usage": MockAccountUsage(),
            "bill_history": [_norm_bill_entry()],
            "due": _norm_due(),
        }
    }


def create_mock_client() -> MagicMock:
    """Create a fully mocked MyTNBClient returning *raw* API shapes."""
    client = MagicMock()
    client.get_customer_accounts = AsyncMock(
        return_value=[MockCustomerAccount()],
    )
    client.get_account_usage_smart = AsyncMock(
        return_value=MockAccountUsage(),
    )
    client.get_bill_history = AsyncMock(
        return_value=_raw_bill_history(),
    )
    client.get_account_due_amount = AsyncMock(
        return_value=_raw_due_amount(),
    )
    client.close = AsyncMock()
    return client


def make_account_dict(
    account_number: str = "220123456789",
    owner_name: str = "Test Owner",
) -> dict[str, str]:
    """Create an account dict for config entry data."""
    return {
        "account_number": account_number,
        "owner_name": owner_name,
    }


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
    """Default v2 config entry data with accounts."""
    return {
        "email": "test@example.com",
        "password": "testpassword",
        "accounts": [make_account_dict()],
    }
