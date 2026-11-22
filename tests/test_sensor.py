"""Tests for sensor.py."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant

from custom_components.mytnb.const import (
    ATTR_ACCOUNT_NUMBER,
    ATTR_ADDRESS,
    ATTR_BILL_DATE,
    ATTR_BILL_HISTORY,
    ATTR_DAILY_USAGE,
    ATTR_DUE_DATE,
    ATTR_IS_SMART_METER,
    ATTR_METER_READINGS,
    ATTR_OWNER_NAME,
    ATTR_PAYMENT_HISTORY,
    ATTR_TARIFF_BLOCKS,
    CONF_ACCOUNTS,
    DOMAIN,
    MONETARY_SENSOR_KEYS,
)
from custom_components.mytnb.sensor import (
    SENSOR_DESCRIPTIONS,
    MyTNBSensor,
    async_setup_entry,
)
from tests.conftest import create_mock_account_data, make_account_dict


def make_coordinator_mock(account_data=None):
    """Create a mock coordinator with given data."""
    if account_data is None:
        account_data = create_mock_account_data()

    coordinator = MagicMock()
    coordinator.data = account_data
    coordinator.hass = MagicMock()
    coordinator.hass.data = {DOMAIN: {}}
    return coordinator


def make_entry_mock(coordinator, accounts=None):
    """Create a mock config entry with accounts in data."""
    if accounts is None:
        accounts = [make_account_dict()]
    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.data = {CONF_ACCOUNTS: accounts}
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


async def test_last_payment_date_returns_date_object(hass: HomeAssistant) -> None:
    """The DATE-device-class sensor must surface a date, not a raw string.

    The library parses myTNB's DD/MM/YYYY into a date; HA calls .isoformat() on
    the value, so a string state would raise "Invalid date". Guards the regression.
    """
    from datetime import date

    from mytnb.models import PaymentHistoryEntry

    data = create_mock_account_data()
    data["220123456789"]["payment_history"] = [
        PaymentHistoryEntry.model_validate(
            {"BillOrPaymentDate": "31/05/2026", "Amount": "87.50",
             "HistoryType": "Payment"}
        )
    ]
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[8],  # last_payment_date
        "220123456789",
    )
    assert sensor.native_value == date(2026, 5, 31)


async def test_last_payment_date_unparseable_returns_none(
    hass: HomeAssistant,
) -> None:
    """An unparseable date degrades to None instead of raising."""
    from mytnb.models import PaymentHistoryEntry

    data = create_mock_account_data()
    data["220123456789"]["payment_history"] = [
        PaymentHistoryEntry.model_validate(
            {"BillOrPaymentDate": "not-a-date", "Amount": "1.0",
             "HistoryType": "Payment"}
        )
    ]
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(coordinator, SENSOR_DESCRIPTIONS[8], "220123456789")
    assert sensor.native_value is None


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


async def test_sensor_has_entity_name_and_device(hass: HomeAssistant) -> None:
    """Test the sensor uses entity translations and a per-account device."""
    data = create_mock_account_data()
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[3],  # projected_cost
        "220123456789",
        "Test Owner",
    )
    assert sensor.has_entity_name is True
    assert sensor.translation_key == "projected_cost"
    assert (DOMAIN, "220123456789") in sensor.device_info["identifiers"]
    assert sensor.device_info["name"] == "myTNB 220123456789"


async def test_sensor_extra_attributes(hass: HomeAssistant) -> None:
    """Test extra state attributes are scoped to the owning sensor."""
    data = create_mock_account_data()
    coordinator = make_coordinator_mock(data)

    # Account metadata is present on every sensor.
    usage_sensor = MyTNBSensor(coordinator, SENSOR_DESCRIPTIONS[0], "220123456789")
    attrs = usage_sensor.extra_state_attributes
    assert attrs[ATTR_ACCOUNT_NUMBER] == "220123456789"
    assert attrs[ATTR_OWNER_NAME] == "Test Owner"
    assert attrs[ATTR_ADDRESS] == "123 Test St, Kuala Lumpur"
    assert attrs[ATTR_IS_SMART_METER] is True
    # Daily usage is scoped to the current_usage sensor only.
    assert len(attrs[ATTR_DAILY_USAGE]) == 1
    assert attrs[ATTR_DAILY_USAGE][0]["usage"] == 15.0
    assert ATTR_BILL_HISTORY not in attrs
    assert ATTR_TARIFF_BLOCKS not in attrs

    # Tariff blocks live on the last_month_usage sensor.
    monthly_sensor = MyTNBSensor(coordinator, SENSOR_DESCRIPTIONS[4], "220123456789")
    monthly_attrs = monthly_sensor.extra_state_attributes
    assert len(monthly_attrs[ATTR_TARIFF_BLOCKS]) == 1
    assert monthly_attrs[ATTR_TARIFF_BLOCKS][0]["rate"] == "0.218"

    # Payment history lives on the last_payment_amount sensor.
    from mytnb.models import PaymentHistoryEntry

    data["220123456789"]["payment_history"] = [
        PaymentHistoryEntry.model_validate(
            {"BillOrPaymentDate": "15/05/2026", "Amount": "100.50",
             "HistoryType": "Payment"}
        ),
        PaymentHistoryEntry.model_validate(
            {"BillOrPaymentDate": "01/06/2026", "Amount": "45.00",
             "HistoryType": "Bill"}
        ),
    ]
    payment_sensor = MyTNBSensor(coordinator, SENSOR_DESCRIPTIONS[7], "220123456789")
    payment_attrs = payment_sensor.extra_state_attributes
    assert len(payment_attrs[ATTR_PAYMENT_HISTORY]) == 2
    assert payment_attrs[ATTR_PAYMENT_HISTORY][0]["amount"] == 100.50
    assert payment_attrs[ATTR_PAYMENT_HISTORY][0]["is_payment"] is True
    assert payment_attrs[ATTR_PAYMENT_HISTORY][1]["is_payment"] is False
    # Bill history is still exposed alongside payment history for backwards compat.
    assert len(payment_attrs[ATTR_BILL_HISTORY]) == 1
    assert payment_attrs[ATTR_BILL_HISTORY][0]["amount"] == 87.50
    assert payment_attrs[ATTR_BILL_HISTORY][0]["date"] == date(2026, 5, 15)

    # Due date lives on the due_amount sensor and is a date, not a raw string.
    due_sensor = MyTNBSensor(coordinator, SENSOR_DESCRIPTIONS[6], "220123456789")
    due_attrs = due_sensor.extra_state_attributes
    assert due_attrs[ATTR_DUE_DATE] == date(2026, 6, 30)
    assert isinstance(due_attrs[ATTR_DUE_DATE], date)
    assert ATTR_PAYMENT_HISTORY not in due_attrs
    assert ATTR_BILL_HISTORY not in due_attrs


async def test_last_payment_amount(hass: HomeAssistant) -> None:
    """Test last_payment_amount returns the first payment entry's amount."""
    from mytnb.models import PaymentHistoryEntry

    data = create_mock_account_data()
    data["220123456789"]["payment_history"] = [
        PaymentHistoryEntry.model_validate(
            {"BillOrPaymentDate": "10/01/2026", "Amount": "55.00",
             "HistoryType": "Bill"}
        ),
        PaymentHistoryEntry.model_validate(
            {"BillOrPaymentDate": "31/05/2026", "Amount": "87.50",
             "HistoryType": "Payment"}
        ),
        PaymentHistoryEntry.model_validate(
            {"BillOrPaymentDate": "15/06/2026", "Amount": "22.00",
             "HistoryType": "Bill"}
        ),
    ]
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[7],  # last_payment_amount
        "220123456789",
    )
    assert sensor.native_value == 87.50


async def test_last_payment_amount_no_payments_returns_none(
    hass: HomeAssistant,
) -> None:
    """Test last_payment_amount returns None when no payment entries exist."""
    from mytnb.models import PaymentHistoryEntry

    data = create_mock_account_data()
    data["220123456789"]["payment_history"] = [
        PaymentHistoryEntry.model_validate(
            {"BillOrPaymentDate": "10/01/2026", "Amount": "55.00",
             "HistoryType": "Bill"}
        ),
    ]
    coordinator = make_coordinator_mock(data)

    sensor = MyTNBSensor(
        coordinator,
        SENSOR_DESCRIPTIONS[7],  # last_payment_amount
        "220123456789",
    )
    assert sensor.native_value is None


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
    assert len(SENSOR_DESCRIPTIONS) == 11


async def test_sensor_state_classes() -> None:
    """Test energy sensor descriptions carry a state class."""
    from homeassistant.components.sensor import SensorDeviceClass

    for desc in SENSOR_DESCRIPTIONS:
        assert desc.key is not None
        # Monetary and date sensors legitimately have no state class, and the
        # estimated meter reading deliberately stays out of statistics.
        if desc.device_class in (
            SensorDeviceClass.MONETARY,
            SensorDeviceClass.DATE,
        ) or desc.key == "estimated_meter_reading":
            continue
        assert desc.state_class is not None


async def test_setup_entry_creates_sensors(hass: HomeAssistant) -> None:
    """Test async_setup_entry creates sensors for configured accounts."""
    data = create_mock_account_data("111111111111")
    coordinator = make_coordinator_mock(data)
    entry = make_entry_mock(coordinator, accounts=[make_account_dict("111111111111")])

    added_entities = []

    await async_setup_entry(
        hass, entry, lambda e: _add_entities(e, added_entities)
    )

    assert len(added_entities) == 11
    assert all(isinstance(e, MyTNBSensor) for e in added_entities)


async def test_setup_entry_no_data(hass: HomeAssistant) -> None:
    """Entities are still created without data; they report unavailable.

    This guards against the "entities unknown until reload" bug: entities
    must exist immediately even if the first refresh has not populated data.
    """
    coordinator = make_coordinator_mock()
    coordinator.data = None
    entry = make_entry_mock(coordinator)

    added_entities = []

    await async_setup_entry(
        hass, entry, lambda e: _add_entities(e, added_entities)
    )

    assert len(added_entities) == 11
    assert all(e.available is False for e in added_entities)


async def test_sensor_available_reflects_account_presence(
    hass: HomeAssistant,
) -> None:
    """Sensor is unavailable when its account is missing from coordinator data."""
    coordinator = make_coordinator_mock(create_mock_account_data("111"))
    coordinator.last_update_success = True

    present = MyTNBSensor(coordinator, SENSOR_DESCRIPTIONS[0], "111")
    missing = MyTNBSensor(coordinator, SENSOR_DESCRIPTIONS[0], "999")

    assert present.available is True
    assert missing.available is False


async def test_setup_entry_multiple_accounts(hass: HomeAssistant) -> None:
    """Test sensors created only for configured accounts, not all in coordinator."""
    # Coordinator has data for 3 accounts
    coord_data = {
        **create_mock_account_data("111"),
        **create_mock_account_data("222"),
        **create_mock_account_data("333"),
    }
    coordinator = make_coordinator_mock(coord_data)

    # But only 2 are configured
    entry = make_entry_mock(
        coordinator,
        accounts=[
            make_account_dict("111"),
            make_account_dict("333"),
        ],
    )

    added_entities = []

    await async_setup_entry(
        hass, entry, lambda e: _add_entities(e, added_entities)
    )

    # 2 accounts × 11 sensors = 22
    assert len(added_entities) == 22
    account_numbers = {e.account_number for e in added_entities}
    assert account_numbers == {"111", "333"}


async def test_setup_entry_no_configured_accounts(hass: HomeAssistant) -> None:
    """Test setup with empty accounts list creates no sensors."""
    coordinator = make_coordinator_mock()
    entry = make_entry_mock(coordinator, accounts=[])

    added_entities = []

    await async_setup_entry(
        hass, entry, lambda e: _add_entities(e, added_entities)
    )

    assert len(added_entities) == 0


def _sensor(key: str, data=None) -> MyTNBSensor:
    description = next(d for d in SENSOR_DESCRIPTIONS if d.key == key)
    return MyTNBSensor(make_coordinator_mock(data), description, "220123456789")


async def test_money_is_in_myr() -> None:
    """Monetary sensors use the ISO 4217 code, and the migration list matches them."""
    from homeassistant.components.sensor import SensorDeviceClass

    monetary = [
        d for d in SENSOR_DESCRIPTIONS if d.device_class == SensorDeviceClass.MONETARY
    ]
    assert {d.native_unit_of_measurement for d in monetary} == {"MYR"}
    assert {d.key for d in monetary} == set(MONETARY_SENSOR_KEYS)


async def test_meter_reading(hass: HomeAssistant) -> None:
    """The meter reading is the kWh register from the latest bill."""
    sensor = _sensor("meter_reading")

    assert sensor.native_value == 10319
    attrs = sensor.extra_state_attributes
    assert attrs[ATTR_BILL_DATE] == date(2026, 5, 15)
    assert [r["unit"] for r in attrs[ATTR_METER_READINGS]] == ["kWh", "kW"]
    assert attrs[ATTR_METER_READINGS][0] == {
        "meter_number": "SIE1052308047669",
        "unit": "kWh",
        "previous_reading": 9750,
        "current_reading": 10319,
        "usage": 569,
    }


async def test_meter_reading_without_readings(hass: HomeAssistant) -> None:
    """No readings (no PDF, or a layout the library can't read) means unknown."""
    data = create_mock_account_data()
    data["220123456789"]["meter_readings"] = []
    sensor = _sensor("meter_reading", data)

    assert sensor.native_value is None
    attrs = sensor.extra_state_attributes
    assert ATTR_METER_READINGS not in attrs
    assert ATTR_BILL_DATE not in attrs


async def test_estimated_meter_reading(hass: HomeAssistant) -> None:
    """The estimate adds this cycle's usage to the billed reading."""
    sensor = _sensor("estimated_meter_reading")

    assert sensor.native_value == 10439  # 10319 + 120
    assert sensor.extra_state_attributes[ATTR_BILL_DATE] == date(2026, 5, 15)
    assert sensor.entity_description.entity_registry_enabled_default is False
    assert sensor.entity_description.state_class is None


async def test_estimated_meter_reading_needs_usage(hass: HomeAssistant) -> None:
    """Without this cycle's usage there is no estimate."""
    data = create_mock_account_data()
    data["220123456789"]["usage"].current_usage_kwh = None

    assert _sensor("estimated_meter_reading", data).native_value is None
