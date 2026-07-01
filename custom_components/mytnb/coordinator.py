"""DataUpdateCoordinator for myTNB integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

import mytnb
from mytnb.exceptions import APIError, AuthenticationError, MyTNBError

from .const import CONF_ACCOUNT_NUMBER, DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class MyTNBDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch myTNB data for configured accounts."""

    def __init__(
        self,
        hass: HomeAssistant,
        email: str,
        password: str,
        accounts: list[dict[str, str]],
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: HomeAssistant instance.
            email: myTNB login email.
            password: myTNB login password.
            accounts: List of account dicts with account_number and owner_name.
        """
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_POLL_INTERVAL,
        )
        self._email = email
        self._password = password
        self._accounts = accounts
        self._client: mytnb.MyTNBClient | None = None

    @property
    def account_numbers(self) -> list[str]:
        """Return the list of configured account numbers."""
        return [acc[CONF_ACCOUNT_NUMBER] for acc in self._accounts]

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest data for configured accounts."""
        if not self._accounts:
            _LOGGER.warning("No accounts configured, skipping data fetch")
            return {}

        client = await self._get_client()
        account_numbers = self.account_numbers

        try:
            # Fetch account metadata once for all configured accounts
            all_accounts = await client.get_customer_accounts()
            account_lookup = {acc.account_number: acc for acc in all_accounts}
            _LOGGER.debug(
                "Discovered %d accounts, fetching data for %d configured",
                len(all_accounts),
                len(account_numbers),
            )

            tasks = [
                self._fetch_account_data(client, acc_no, account_lookup)
                for acc_no in account_numbers
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        except (APIError, MyTNBError) as err:
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

        data: dict[str, dict] = {}
        for acc_no, result in zip(account_numbers, results, strict=True):
            if isinstance(result, Exception):
                _LOGGER.warning(
                    "Failed fetching data for account %s: %s",
                    acc_no,
                    result,
                )
                continue
            data[acc_no] = {
                "account": result["account"],
                "usage": result["usage"],
                "bill_history": result["bill_history"],
                "due": result["due"],
            }

        return data

    async def _get_client(self) -> mytnb.MyTNBClient:
        """Return an authenticated client, re-logging in if needed."""
        if self._client is None:
            self._client = await mytnb.MyTNBClient.login(
                self._email, self._password
            )
            _LOGGER.debug("Logged in as %s", self._email)
            return self._client

        try:
            # Light session check: re-discover accounts to verify session
            await self._client.get_customer_accounts()
        except (AuthenticationError, APIError):
            _LOGGER.debug("Session expired, re-logging in")
            self._client = await mytnb.MyTNBClient.login(
                self._email, self._password
            )

        return self._client

    async def _fetch_account_data(
        self,
        client: mytnb.MyTNBClient,
        account_number: str,
        account_lookup: dict[str, Any],
    ) -> dict:
        """Fetch usage, bill history, due amount, and account metadata."""
        usage, bill_history_raw, due_raw = await asyncio.gather(
            client.get_account_usage_smart(account_number),
            client.get_bill_history(account_number),
            client.get_account_due_amount(account_number),
        )
        return {
            "usage": usage,
            "bill_history": self._normalize_bill_history(bill_history_raw),
            "due": self._normalize_due(due_raw),
            "account": account_lookup.get(account_number),
        }

    @staticmethod
    def _normalize_due(raw: dict) -> dict[str, Any]:
        """Normalize the due-amount payload into a stable schema.

        Raw shape: {"AccountAmountDue": {"amountDue": "12.34", "billDueDate": "..."}}
        Normalized: {"amount_due": 12.34, "due_date": "..."}
        """
        inner = raw.get("AccountAmountDue", raw) if isinstance(raw, dict) else {}
        if not isinstance(inner, dict):
            return {"amount_due": None, "due_date": None}

        amount = inner.get("amountDue")
        return {
            "amount_due": float(amount) if amount is not None else None,
            "due_date": inner.get("billDueDate"),
        }

    @staticmethod
    def _normalize_bill_history(raw: list) -> list[dict[str, Any]]:
        """Normalize bill-history entries into a stable schema.

        Raw shape: [{"DtBill": "2026-01-15", "AmPayable": "87.50", ...}]
        Normalized: [{"date": "2026-01-15", "amount": 87.50}]
        """
        if not isinstance(raw, list):
            return []

        normalized = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            amount = entry.get("AmPayable")
            normalized.append({
                "date": entry.get("DtBill"),
                "amount": float(amount) if amount is not None else None,
            })
        return normalized
