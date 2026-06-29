"""DataUpdateCoordinator for myTNB integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

import mytnb
from mytnb.exceptions import APIError, AuthenticationError, MyTNBError

from .const import DEFAULT_POLL_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class MyTNBDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch myTNB data for all linked accounts."""

    def __init__(self, hass: HomeAssistant, email: str, password: str) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=DEFAULT_POLL_INTERVAL,
        )
        self._email = email
        self._password = password
        self._client: mytnb.MyTNBClient | None = None

    async def _async_update_data(self) -> dict[str, dict]:
        """Fetch latest data for all accounts."""
        client = await self._get_client()

        try:
            accounts = await client.get_customer_accounts()
            _LOGGER.debug("Discovered %d accounts", len(accounts))

            tasks = [
                self._fetch_account_data(client, acc.account_number)
                for acc in accounts
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        except (APIError, MyTNBError) as err:
            raise UpdateFailed(f"API error: {err}") from err

        data: dict[str, dict] = {}
        for acc, result in zip(accounts, results, strict=True):
            if isinstance(result, Exception):
                _LOGGER.warning(
                    "Failed fetching data for account %s: %s",
                    acc.account_number,
                    result,
                )
                continue
            data[acc.account_number] = {
                "account": acc,
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
            await self._client.get_customer_accounts()
        except (AuthenticationError, APIError):
            _LOGGER.debug("Session expired, re-logging in")
            self._client = await mytnb.MyTNBClient.login(
                self._email, self._password
            )

        return self._client

    @staticmethod
    async def _fetch_account_data(
        client: mytnb.MyTNBClient, account_number: str
    ) -> dict:
        """Fetch usage, bill history, and due amount for a single account."""
        usage, bill_history, due = await asyncio.gather(
            client.get_account_usage_smart(account_number),
            client.get_bill_history(account_number),
            client.get_account_due_amount(account_number),
        )
        return {
            "usage": usage,
            "bill_history": bill_history,
            "due": due,
        }
