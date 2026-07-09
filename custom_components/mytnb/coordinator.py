"""DataUpdateCoordinator for myTNB integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

import mytnb
from mytnb.exceptions import APIError, AuthenticationError, MyTNBError

from .const import (
    CONF_ACCOUNT_NUMBER,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_RETRY_BACKOFF_FACTOR,
    DEFAULT_RETRY_BASE_DELAY,
    DOMAIN,
)
from .retry import with_retry
from .statistics import async_import_daily_statistics

_LOGGER = logging.getLogger(__name__)

T = TypeVar("T")


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
        # Retry/backoff tuning (mirrors python-mytnb's internal cadence so a
        # transient failure that slips past the library's per-request retries
        # gets a bounded second chance within the same poll cycle).
        self._retry_attempts = DEFAULT_RETRY_ATTEMPTS
        self._retry_base_delay = DEFAULT_RETRY_BASE_DELAY
        self._retry_backoff_factor = DEFAULT_RETRY_BACKOFF_FACTOR

    @property
    def account_numbers(self) -> list[str]:
        """Return the list of configured account numbers."""
        return [acc[CONF_ACCOUNT_NUMBER] for acc in self._accounts]

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch latest data for configured accounts."""
        if not self._accounts:
            _LOGGER.warning("No accounts configured, skipping data fetch")
            return {}

        account_numbers = self.account_numbers

        try:
            all_accounts = await self._discover_accounts()
            account_lookup = {acc.account_number: acc for acc in all_accounts}
            _LOGGER.debug(
                "Discovered %d accounts, fetching data for %d configured",
                len(all_accounts),
                len(account_numbers),
            )

            # _discover_accounts() guarantees a non-None client above.
            client = self._client
            assert client is not None
            tasks = [
                self._fetch_account_data(client, acc_no, account_lookup)
                for acc_no in account_numbers
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        except ConfigEntryAuthFailed:
            raise
        except (APIError, MyTNBError) as err:
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err

        # Start from the previously-known data so that when *some* accounts
        # succeed, a transient failure on another keeps its last value instead
        # of flapping to unavailable.
        data: dict[str, dict] = dict(self.data or {})
        succeeded = 0
        for acc_no, result in zip(account_numbers, results, strict=True):
            if isinstance(result, Exception):
                _LOGGER.warning(
                    "Failed fetching data for account %s: %s",
                    acc_no,
                    result,
                )
                continue
            succeeded += 1
            data[acc_no] = {
                "account": result["account"],
                "usage": result["usage"],
                "bill_history": result["bill_history"],
                "payment_history": result["payment_history"],
                "due": result["due"],
            }
            await self._backfill_statistics(
                acc_no, result["account"], result["usage"]
            )

        # If nothing at all succeeded this cycle, treat it as a real failure.
        # On first refresh this becomes ConfigEntryNotReady (HA retries setup);
        # afterwards it marks entities unavailable while self.data retains the
        # last-known values for when the API recovers.
        if succeeded == 0:
            raise UpdateFailed("Failed fetching data for all configured accounts")

        # Only keep accounts that are still configured.
        return {acc_no: data[acc_no] for acc_no in account_numbers if acc_no in data}

    async def _retry(self, send: Callable[[], Awaitable[T]]) -> T:
        """Wrap ``send`` with the coordinator's retry/backoff policy."""
        return await with_retry(
            send,
            attempts=self._retry_attempts,
            base_delay=self._retry_base_delay,
            backoff_factor=self._retry_backoff_factor,
            logger=_LOGGER,
        )

    async def _discover_accounts(self) -> list[Any]:
        """Discover linked accounts, logging in / re-logging in as needed.

        This is the single per-cycle call that both verifies the session and
        returns account metadata, avoiding a redundant second request.
        """
        client = await self._get_client()
        try:
            return await self._retry(client.get_customer_accounts)
        except AuthenticationError:
            _LOGGER.debug("Session expired, re-logging in")
            try:
                self._client = await mytnb.MyTNBClient.login(
                    self._email, self._password
                )
                return await self._retry(self._client.get_customer_accounts)
            except AuthenticationError as err:
                raise ConfigEntryAuthFailed(
                    f"Authentication failed for {self._email}"
                ) from err

    async def _get_client(self) -> mytnb.MyTNBClient:
        """Return an authenticated client, logging in on first use."""
        if self._client is None:
            try:
                self._client = await mytnb.MyTNBClient.login(
                    self._email, self._password
                )
            except AuthenticationError as err:
                raise ConfigEntryAuthFailed(
                    f"Authentication failed for {self._email}"
                ) from err
            _LOGGER.debug("Logged in as %s", self._email)
        return self._client

    async def _backfill_statistics(
        self,
        account_number: str,
        account: Any,
        usage: Any,
    ) -> None:
        """Import the daily energy/cost series as long-term statistics.

        Never allowed to fail the coordinator update — the recorder may be
        unavailable, and stale statistics are not worth losing live data over.
        """
        if not (usage and usage.by_day):
            return
        owner_name = account.owner_name if account is not None else ""
        try:
            await async_import_daily_statistics(
                self.hass, account_number, owner_name, usage
            )
        except Exception as err:  # noqa: BLE001 - stats must never break updates
            _LOGGER.warning(
                "Failed importing statistics for account %s: %s",
                account_number,
                err,
                exc_info=True,
            )

    async def _fetch_account_data(
        self,
        client: mytnb.MyTNBClient,
        account_number: str,
        account_lookup: dict[str, Any],
    ) -> dict:
        """Fetch usage, bill history, payment history, due amount, and account metadata.

        The python-mytnb client already returns typed models, so no
        normalization is needed here. Passing a ``CustomerAccount`` lets the
        library derive ``is_owner`` and ``account_type`` automatically. The
        four read calls run concurrently and share a single retry envelope so
        a transient blip (which per-request retries inside the library didn't catch,
        or which slipped through) gets one more bounded attempt with backoff rather
        than failing the whole account.
        """
        account = account_lookup.get(account_number)
        account_ref = account or account_number

        async def _fetch_all() -> dict:
            usage, bill_history, payment_history, due = await asyncio.gather(
                client.get_account_usage_smart(account_ref),
                client.get_bill_history(account_ref),
                client.get_payment_history(account_ref),
                client.get_account_due_amount(account_ref),
            )
            return {
                "usage": usage,
                "bill_history": bill_history,
                "payment_history": payment_history,
                "due": due,
                "account": account,
            }

        return await self._retry(_fetch_all)
