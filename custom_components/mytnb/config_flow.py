"""Config flow for myTNB integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers import selector

import mytnb
from mytnb.exceptions import (
    APIError,
    AuthenticationError,
    GeoBlockedError,
    MyTNBError,
)

from .const import CONF_ACCOUNT_NUMBER, CONF_ACCOUNTS, CONF_OWNER_NAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate_login(
    email: str, password: str
) -> list[dict[str, str]]:
    """Validate login credentials and return discovered accounts.

    Returns a list of dicts with account_number and owner_name.
    """
    client = await mytnb.MyTNBClient.login(email, password)
    accounts = await client.get_customer_accounts()
    return [
        {
            CONF_ACCOUNT_NUMBER: acc.account_number,
            CONF_OWNER_NAME: acc.owner_name,
        }
        for acc in accounts
    ]


def _build_accounts_schema(
    discovered: list[dict[str, str]],
    preselected: set[str] | None = None,
) -> vol.Schema:
    """Build a multi-select schema for account selection.

    Args:
        discovered: List of account dicts with account_number and owner_name.
        preselected: Set of account numbers to pre-select (None = none selected).
    """
    options = {
        acc[CONF_ACCOUNT_NUMBER]: (
            f"{acc[CONF_OWNER_NAME]} ({acc[CONF_ACCOUNT_NUMBER]})"
        )
        for acc in discovered
    }

    default = list(preselected) if preselected else []

    return vol.Schema(
        {
            vol.Required(CONF_ACCOUNTS, default=default): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=k, label=v)
                        for k, v in options.items()
                    ],
                    multiple=True,
                    sort=True,
                ),
            ),
        }
    )


class MyTNBConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for myTNB."""

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._discovered: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: collect credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            try:
                self._discovered = await _validate_login(email, password)
            except AuthenticationError:
                errors["base"] = "auth"
            except GeoBlockedError:
                errors["base"] = "geo_blocked"
            except APIError:
                errors["base"] = "api_error"
            except MyTNBError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(email)
                self._abort_if_unique_id_configured()

                if not self._discovered:
                    errors["base"] = "no_accounts"
                else:
                    # Store credentials for later steps
                    self._email = email
                    self._password = password
                    return await self.async_step_accounts()

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_accounts(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle account selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected: list[str] = user_input.get(CONF_ACCOUNTS, [])

            if not selected:
                errors[CONF_ACCOUNTS] = "select_at_least_one"
            else:
                accounts = [
                    acc
                    for acc in self._discovered
                    if acc[CONF_ACCOUNT_NUMBER] in selected
                ]
                return self.async_create_entry(
                    title=f"myTNB ({self._email})",
                    data={
                        CONF_EMAIL: self._email,
                        CONF_PASSWORD: self._password,
                        CONF_ACCOUNTS: accounts,
                    },
                )

        return self.async_show_form(
            step_id="accounts",
            data_schema=_build_accounts_schema(self._discovered),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the options flow."""
        return MyTNBOptionsFlow(config_entry)


class MyTNBOptionsFlow(OptionsFlow):
    """Handle options flow for myTNB — reconfigure selected accounts."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize the options flow."""
        super().__init__()
        self._entry = config_entry
        self._discovered: list[dict[str, str]] = []

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage account selection."""
        errors: dict[str, str] = {}

        data = dict(self._entry.data)
        configured_accounts: list[dict[str, str]] = data.get(CONF_ACCOUNTS, [])
        configured_numbers = {
            acc[CONF_ACCOUNT_NUMBER] for acc in configured_accounts
        }

        # Discover current accounts from API
        if not self._discovered:
            try:
                self._discovered = await _validate_login(
                    data[CONF_EMAIL], data[CONF_PASSWORD]
                )
            except (AuthenticationError, APIError, GeoBlockedError):
                errors["base"] = "api_error"
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema({}),
                    errors=errors,
                )
            except MyTNBError:
                errors["base"] = "unknown"
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema({}),
                    errors=errors,
                )

        if user_input is not None:
            selected: list[str] = user_input.get(CONF_ACCOUNTS, [])

            if not selected:
                errors[CONF_ACCOUNTS] = "select_at_least_one"
            else:
                accounts = [
                    acc
                    for acc in self._discovered
                    if acc[CONF_ACCOUNT_NUMBER] in selected
                ]
                new_data = {**data, CONF_ACCOUNTS: accounts}
                self.hass.config_entries.async_update_entry(
                    self._entry, data=new_data
                )
                return self.async_create_entry(
                    title="",
                    data={},
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_build_accounts_schema(
                self._discovered, preselected=configured_numbers
            ),
            errors=errors,
        )
