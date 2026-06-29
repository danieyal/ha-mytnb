"""Tests for sensor.py."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from custom_components.mytnb.const import (
    ATTR_ACCOUNT_NUMBER,
    ATTR_ADDRESS,
    ATTR_BILL_HISTORY,
    ATTR_DAILY_USAGE,
    ATTR_IS_SMART_METER,
    ATTR_OWNER_NAME,
    ATTR_TARIFF_BLOCKS,
    DOMAIN,
)
from custom_components.mytnb.sensor import (
    SENSOR_DESCRIPTIONS,
    MyTNBSensor,
    async_setup_entry,
)
from tests.conftest import create_mock_account_data


def make_coordinator_mock(account_data=None):
    """Create a mock coordinator with given data."""
    if account_data is None:
        account_data = create_mock_account_data()

    coordinator = MagicMock()
    coordinator.data = account_data
    coordinator.hass = MagicMock()
    coordinator.hass.data = {DOMAIN: {}}
    return coordinator


def make_entry_mock(coordinator):
    """Create a mock config entry."""
    entry = MagicMock()
    entry.runtime_data = coordinator
    return entry


def _add_entities(entities, target):
    """Add entities to the target list."""
    target.extend(entities)


async def test_sensor_native_value(hass: HomeAssistant) -> None:
    """Test sensor native values are correct."""
    data = create_mock_account_data()
    coordinator = make_coordinator_mock(data)

    usage_sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[0],  # current_usage
        "220123456789",
    )
    assert usage_sensor.native_value == 120.0

    cost_sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[2],  # current_cost
        "220123456789",
    )
    assert cost_sensor.native_value == 26.16

    due_sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[6],  # due_amount
        "220123456789",
    )
    assert due_sensor.native_value == 26.16


async def test_sensor_native_value_when_none(hass: HomeAssistant) -> None:
    """Test sensor returns None when coordinator has no data."""
    coordinator = make_coordinator_mock()
    coordinator.data = None

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[0],
        "220123456789",
    )
    assert sensor.native_value is None


async def test_sensor_native_value_missing_account(
    hass: HomeAssistant,
) -> None:
    """Test sensor returns None when account not in data."""
    coordinator = make_coordinator_mock(
        create_mock_account_data("111111111111")
    )

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[0],
        "999999999999",
    )
    assert sensor.native_value is None


async def test_sensor_unique_id(hass: HomeAssistant) -> None:
    """Test sensor unique_id format."""
    data = create_mock_account_data()
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[0],
        "220123456789",
    )
    assert sensor.unique_id == "mytnb_220123456789_current_usage"


async def test_sensor_name(hass: HomeAssistant) -> None:
    """Test sensor name format."""
    data = create_mock_account_data()
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[3],  # projected_cost
        "220123456789",
    )
    assert sensor.name == "myTNB 220123456789 Projected Cost"


async def test_sensor_extra_attributes(hass: HomeAssistant) -> None:
    """Test extra state attributes."""
    data = create_mock_account_data()
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[0],
        "220123456789",
    )

    attrs = sensor.extra_state_attributes

    assert attrs[ATTR_ACCOUNT_NUMBER] == "220123456789"
    assert attrs[ATTR_OWNER_NAME] == "Test Owner"
    assert attrs[ATTR_ADDRESS] == "123 Test St, Kuala Lumpur"
    assert attrs[ATTR_IS_SMART_METER] is True
    assert len(attrs[ATTR_BILL_HISTORY]) == 1
    assert attrs[ATTR_BILL_HISTORY][0]["amount"] == 87.50
    assert len(attrs[ATTR_TARIFF_BLOCKS]) == 1
    assert attrs[ATTR_TARIFF_BLOCKS][0]["rate"] == 0.218
    assert len(attrs[ATTR_DAILY_USAGE]) == 1
    assert attrs[ATTR_DAILY_USAGE][0]["usage"] == 15.0


async def test_sensor_extra_attributes_none_when_no_data(
    hass: HomeAssistant,
) -> None:
    """Test extra attributes return None when coordinator has no data."""
    coordinator = make_coordinator_mock()
    coordinator.data = None

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[0],
        "220123456789",
    )
    assert sensor.extra_state_attributes is None


async def test_sensor_descriptions_count() -> None:
    """Test we have the expected number of sensor descriptions."""
    assert len(SENSOR_DESCRIPTIONS) == 9


async def test_sensor_state_classes() -> None:
    """Test sensor descriptions have valid state classes."""
    for desc in SENSOR_DESCRIPTIONS:
        assert desc.state_class is not None
        assert desc.key is not None


async def test_setup_entry_creates_sensors(hass: HomeAssistant) -> None:
    """Test async_setup_entry creates sensors for all accounts."""
    data = create_mock_account_data("111111111111")
    coordinator = make_coordinator_mock(data)
    entry = make_entry_mock(coordinator)

    added_entities = []

    await async_setup_entry(
        hass, entry, lambda e: _add_entities(e, added_entities)
    )

    assert len(added_entities) == 9
    assert all(isinstance(e, MyTNBSensor) for e in added_entities)


async def test_setup_entry_no_data(hass: HomeAssistant) -> None:
    """Test async_setup_entry handles no coordinator data."""
    coordinator = make_coordinator_mock()
    coordinator.data = None
    entry = make_entry_mock(coordinator)

    added_entities = []

    await async_setup_entry(
        hass, entry, lambda e: _add_entities(e, added_entities)
    )

    assert len(added_entities) == 0


async def test_last_payment_date_sensor(hass: HomeAssistant) -> None:
    """Test last_payment_date sensor returns date."""
    data = create_mock_account_data()
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[8],  # last_payment_date
        "220123456789",
    )
    assert sensor.native_value == date(2026, 5, 15)


async def test_monthly_usage_sensor(hass: HomeAssistant) -> None:
    """Test monthly_usage sensor returns correct value."""
    data = create_mock_account_data()
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[4],  # monthly_usage
        "220123456789",
    )
    assert sensor.native_value == 450.0
    assert sensor.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR


async def test_due_amount_sensor(hass: HomeAssistant) -> None:
    """Test due_amount sensor."""
    data = create_mock_account_data()
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[6],  # due_amount
        "220123456789",
    )
    assert sensor.native_value == 26.16
    assert sensor.native_unit_of_measurement == "RM"
