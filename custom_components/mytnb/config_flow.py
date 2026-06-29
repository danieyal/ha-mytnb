"""Config flow for myTNB integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from mytnb import MyTNBClient
from mytnb.exceptions import APIError, AuthenticationError, GeoBlockedError, MyTNBError

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


async def _validate_login(email: str, password: str) -> None:
    """Validate login credentials and account discovery."""
    client = await MyTNBClient.login(email, password)
    await client.get_customer_accounts()


class MyTNBConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for myTNB."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]

            try:
                await asyncio.wait_for(
                    _validate_login(email, password), timeout=30
                )
            except AuthenticationError:
                errors["base"] = "auth"
            except GeoBlockedError:
                errors["base"] = "geo_blocked"
            except APIError:
                errors["base"] = "api_error"
            except MyTNBError:
                errors["base"] = "unknown"
            except TimeoutError:
                errors["base"] = "api_error"
            else:
                await self.async_set_unique_id(email)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"myTNB ({email})",
                    data={
                        CONF_EMAIL: email,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )
