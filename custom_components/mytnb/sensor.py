"""Sensor platform for myTNB integration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import MyTNBConfigEntry
from .const import (
    ATTR_ACCOUNT_NUMBER,
    ATTR_ADDRESS,
    ATTR_BILL_HISTORY,
    ATTR_DAILY_USAGE,
    ATTR_DUE_DATE,
    ATTR_IS_SMART_METER,
    ATTR_OWNER_NAME,
    ATTR_TARIFF_BLOCKS,
    CONF_ACCOUNT_NUMBER,
    CONF_ACCOUNTS,
    CONF_OWNER_NAME,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)
from .coordinator import MyTNBDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CURRENCY_RM = "RM"


@dataclass(frozen=True, kw_only=True)
class MyTNBSensorEntityDescription(SensorEntityDescription):
    """Description for a myTNB sensor derived from a single account."""

    value_fn: Callable[[dict[str, Any]], StateType]
    # Names of large/detailed attribute blocks to expose on *this* sensor only
    # (keeps big lists off every entity to avoid recorder bloat).
    attr_keys: tuple[str, ...] = field(default_factory=tuple)


SENSOR_DESCRIPTIONS: list[MyTNBSensorEntityDescription] = [
    MyTNBSensorEntityDescription(
        key="current_usage",
        translation_key="current_usage",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data["usage"].current_usage_kwh,
        attr_keys=(ATTR_DAILY_USAGE,),
    ),
    MyTNBSensorEntityDescription(
        key="average_usage",
        translation_key="average_usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["usage"].average_usage_kwh,
    ),
    MyTNBSensorEntityDescription(
        key="current_cost",
        translation_key="current_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_RM,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data["usage"].current_cost_rm,
    ),
    MyTNBSensorEntityDescription(
        key="projected_cost",
        translation_key="projected_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_RM,
        value_fn=lambda data: data["usage"].projected_cost_rm,
    ),
    MyTNBSensorEntityDescription(
        key="monthly_usage",
        translation_key="monthly_usage",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: (
            data["usage"].by_month.months[0].usage_kwh
            if data["usage"].by_month and data["usage"].by_month.months
            else None
        ),
        attr_keys=(ATTR_TARIFF_BLOCKS,),
    ),
    MyTNBSensorEntityDescription(
        key="monthly_cost",
        translation_key="monthly_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_RM,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: (
            data["usage"].by_month.months[0].amount_rm
            if data["usage"].by_month and data["usage"].by_month.months
            else None
        ),
    ),
    MyTNBSensorEntityDescription(
        key="due_amount",
        translation_key="due_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_RM,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda data: data["due"]["amount_due"],
        attr_keys=(ATTR_DUE_DATE,),
    ),
    MyTNBSensorEntityDescription(
        key="last_payment_amount",
        translation_key="last_payment_amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement=CURRENCY_RM,
        value_fn=lambda data: (
            data["bill_history"][0]["amount"] if data["bill_history"] else None
        ),
        attr_keys=(ATTR_BILL_HISTORY,),
    ),
    MyTNBSensorEntityDescription(
        key="last_payment_date",
        translation_key="last_payment_date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: (
            data["bill_history"][0]["date"] if data["bill_history"] else None
        ),
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MyTNBConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up myTNB sensors from a config entry.

    Entities are created for every configured account regardless of whether
    data has arrived yet — they simply report as unavailable until the
    coordinator has data for that account. This means entities appear
    immediately on first setup instead of only after a reload.
    """
    coordinator: MyTNBDataUpdateCoordinator = entry.runtime_data
    accounts: list[dict[str, str]] = entry.data.get(CONF_ACCOUNTS, [])

    entities = [
        MyTNBSensor(
            coordinator,
            desc,
            acc[CONF_ACCOUNT_NUMBER],
            acc.get(CONF_OWNER_NAME, ""),
        )
        for acc in accounts
        for desc in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class MyTNBSensor(CoordinatorEntity[MyTNBDataUpdateCoordinator], SensorEntity):
    """Sensor representing a single metric for a myTNB account."""

    entity_description: MyTNBSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: MyTNBDataUpdateCoordinator,
        description: MyTNBSensorEntityDescription,
        account_number: str,
        owner_name: str = "",
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self.account_number = account_number

        self._attr_unique_id = f"{DOMAIN}_{account_number}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_number)},
            name=owner_name or f"myTNB {account_number}",
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def _account_data(self) -> dict[str, Any] | None:
        """Return this account's slice of coordinator data, if present."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.account_number)

    @property
    def available(self) -> bool:
        """Return True only when we have fresh data for this account."""
        return super().available and self._account_data is not None

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        data = self._account_data
        if data is None:
            return None
        try:
            return self.entity_description.value_fn(data)
        except (AttributeError, KeyError, IndexError, TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return entity-specific state attributes."""
        data = self._account_data
        if data is None:
            return None

        attrs: dict[str, Any] = {ATTR_ACCOUNT_NUMBER: self.account_number}

        account = data.get("account")
        if account is not None:
            attrs[ATTR_OWNER_NAME] = account.owner_name
            attrs[ATTR_ADDRESS] = account.account_st_address
            attrs[ATTR_IS_SMART_METER] = account.is_smart_meter

        for key in self.entity_description.attr_keys:
            value = _build_attribute(key, data)
            if value is not None:
                attrs[key] = value

        return attrs


def _build_attribute(key: str, data: dict[str, Any]) -> Any:
    """Build a large/detailed attribute block on demand."""
    usage = data.get("usage")

    if key == ATTR_DUE_DATE:
        return data.get("due", {}).get("due_date")

    if key == ATTR_BILL_HISTORY:
        bill_history = data.get("bill_history") or []
        if not bill_history:
            return None
        return [
            {"date": bill.get("date"), "amount": bill.get("amount")}
            for bill in bill_history
        ]

    if key == ATTR_TARIFF_BLOCKS:
        if not (usage and usage.by_month and usage.by_month.months):
            return None
        month = usage.by_month.months[0]
        if not month.tariff_blocks:
            return None
        return [
            {
                "block": block.block_id,
                "rate": block.block_pricing,
                "usage": block.usage,
                "cost": block.amount,
            }
            for block in month.tariff_blocks
        ]

    if key == ATTR_DAILY_USAGE:
        if not (usage and usage.by_day):
            return None
        days = [
            {
                "date": day.date,
                "usage": day.consumption_kwh,
                "cost": day.amount_rm,
            }
            for week in usage.by_day
            for day in week.days
        ]
        return days or None

    return None
