"""Sensor platform for myTNB integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MyTNBConfigEntry
from .const import (
    ATTR_ACCOUNT_NUMBER,
    ATTR_ADDRESS,
    ATTR_BILL_HISTORY,
    ATTR_DAILY_USAGE,
    ATTR_IS_SMART_METER,
    ATTR_OWNER_NAME,
    ATTR_TARIFF_BLOCKS,
    CONF_ACCOUNT_NUMBER,
    CONF_ACCOUNTS,
    DOMAIN,
)
from .coordinator import MyTNBDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CURRENCY_RM = "RM"


def _safe_isoformat(value: date | datetime | str) -> str:
    """Return ISO format string for a date/datetime, or the value as-is."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


@dataclass(frozen=True, kw_only=True)
class MyTNBSensorEntityDescription(SensorEntityDescription):
    """Description for a myTNB sensor derived from a single account."""

    value_fn: callable


SENSOR_DESCRIPTIONS: list[MyTNBSensorEntityDescription] = [
    MyTNBSensorEntityDescription(
        key="current_usage",
        translation_key="current_usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data["usage"].current_usage,
    ),
    MyTNBSensorEntityDescription(
        key="average_usage",
        translation_key="average_usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["usage"].average_usage,
    ),
    MyTNBSensorEntityDescription(
        key="current_cost",
        translation_key="current_cost",
        native_unit_of_measurement=CURRENCY_RM,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data["usage"].current_cost,
    ),
    MyTNBSensorEntityDescription(
        key="projected_cost",
        translation_key="projected_cost",
        native_unit_of_measurement=CURRENCY_RM,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["usage"].projected_cost,
    ),
    MyTNBSensorEntityDescription(
        key="monthly_usage",
        translation_key="monthly_usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: (
            data["usage"].by_month.months[0].usage_total
            if data["usage"].by_month and data["usage"].by_month.months
            else None
        ),
    ),
    MyTNBSensorEntityDescription(
        key="monthly_cost",
        translation_key="monthly_cost",
        native_unit_of_measurement=CURRENCY_RM,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: (
            data["usage"].by_month.months[0].amount_total
            if data["usage"].by_month and data["usage"].by_month.months
            else None
        ),
    ),
    MyTNBSensorEntityDescription(
        key="due_amount",
        translation_key="due_amount",
        native_unit_of_measurement=CURRENCY_RM,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data["due"]["amount_due"],
    ),
    MyTNBSensorEntityDescription(
        key="last_payment_amount",
        translation_key="last_payment_amount",
        native_unit_of_measurement=CURRENCY_RM,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            data["bill_history"][0]["amount"]
            if data["bill_history"]
            else None
        ),
    ),
    MyTNBSensorEntityDescription(
        key="last_payment_date",
        translation_key="last_payment_date",
        device_class="date",
        value_fn=lambda data: (
            data["bill_history"][0]["date"]
            if data["bill_history"]
            else None
        ),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyTNBConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up myTNB sensors from a config entry."""
    coordinator: MyTNBDataUpdateCoordinator = entry.runtime_data

    if coordinator.data is None:
        return

    accounts: list[dict[str, str]] = entry.data.get(CONF_ACCOUNTS, [])

    entities = []
    for acc in accounts:
        account_number = acc[CONF_ACCOUNT_NUMBER]
        for desc in SENSOR_DESCRIPTIONS:
            entities.append(
                MyTNBSensor(coordinator, desc, account_number)
            )
    async_add_entities(entities)


class MyTNBSensor(CoordinatorEntity, SensorEntity):
    """Sensor representing a single metric for a myTNB account."""

    entity_description: MyTNBSensorEntityDescription

    def __init__(
        self,
        coordinator: MyTNBDataUpdateCoordinator,
        description: MyTNBSensorEntityDescription,
        account_number: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.account_number = account_number

        self._attr_unique_id = f"{DOMAIN}_{account_number}_{description.key}"
        self._attr_name = (
            f"myTNB {account_number} {description.key.replace('_', ' ').title()}"
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        data = self.coordinator.data.get(self.account_number)
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity specific state attributes."""
        if self.coordinator.data is None:
            return None
        data = self.coordinator.data.get(self.account_number)
        if data is None:
            return None

        account = data["account"]
        usage = data["usage"]
        bill_history = data["bill_history"]

        attrs: dict[str, Any] = {
            ATTR_ACCOUNT_NUMBER: account.account_number,
            ATTR_OWNER_NAME: account.owner_name,
            ATTR_ADDRESS: account.address,
            ATTR_IS_SMART_METER: account.is_smart_meter,
        }

        if bill_history:
            attrs[ATTR_BILL_HISTORY] = [
                {
                    "date": _safe_isoformat(bill["date"]),
                    "amount": bill["amount"],
                }
                for bill in bill_history
            ]

        if usage and usage.by_month and usage.by_month.months:
            month = usage.by_month.months[0]
            if month.tariff_blocks:
                attrs[ATTR_TARIFF_BLOCKS] = [
                    {
                        "block": block.block,
                        "rate": block.rate,
                        "usage": block.usage,
                        "cost": block.cost,
                    }
                    for block in month.tariff_blocks
                ]

        if usage and usage.daily and usage.daily.days:
            attrs[ATTR_DAILY_USAGE] = [
                {
                    "date": _safe_isoformat(day.date),
                    "usage": day.usage,
                    "cost": day.cost,
                }
                for day in usage.daily.days
            ]

        return attrs
