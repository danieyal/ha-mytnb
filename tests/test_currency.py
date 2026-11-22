"""Tests for relabelling RM statistics as MYR, against a real recorder."""

from __future__ import annotations

from datetime import timedelta
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    async_import_statistics,
    get_metadata,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.mytnb import _async_relabel_currency
from custom_components.mytnb.const import CONF_ACCOUNTS, DOMAIN
from custom_components.mytnb.statistics import async_relabel_currency
from tests.conftest import make_account_dict

_ENTRY_DATA = {
    CONF_EMAIL: "test@example.com",
    CONF_PASSWORD: "testpassword",
    CONF_ACCOUNTS: [make_account_dict()],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Set up the recorder before hass starts, then enable custom integrations."""


async def _statistics_units(hass: HomeAssistant, statistic_ids: set[str]) -> dict:
    metadata = await get_instance(hass).async_add_executor_job(
        partial(get_metadata, hass, statistic_ids=statistic_ids)
    )
    return {sid: meta["unit_of_measurement"] for sid, (_, meta) in metadata.items()}


def _seed_statistic(hass: HomeAssistant, statistic_id: str, unit: str) -> None:
    source = statistic_id.split(":")[0] if ":" in statistic_id else "recorder"
    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        mean_type=StatisticMeanType.NONE,
        name=None,
        source=source,
        statistic_id=statistic_id,
        unit_class=None,
        unit_of_measurement=unit,
    )
    hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    start = hour - timedelta(hours=2)
    rows = [StatisticData(start=start, state=10.0, sum=10.0)]
    if source == "recorder":
        async_import_statistics(hass, metadata, rows)
    else:
        async_add_external_statistics(hass, metadata, rows)


async def test_relabels_rm_statistics(hass: HomeAssistant) -> None:
    """The entry's RM statistics become MYR; other units and entities stay."""
    registry = er.async_get(hass)
    cost = registry.async_get_or_create(
        "sensor", DOMAIN, f"{DOMAIN}_220123456789_current_cost"
    ).entity_id
    due = registry.async_get_or_create(
        "sensor", DOMAIN, f"{DOMAIN}_220123456789_due_amount"
    ).entity_id
    usage = registry.async_get_or_create(
        "sensor", DOMAIN, f"{DOMAIN}_220123456789_current_usage"
    ).entity_id
    daily_cost = "mytnb:220123456789_daily_cost"
    daily_energy = "mytnb:220123456789_daily_energy"
    other = "sensor.someone_elses_rm_sensor"

    _seed_statistic(hass, cost, "RM")
    _seed_statistic(hass, due, "MYR")  # already fixed by hand
    _seed_statistic(hass, usage, "kWh")
    _seed_statistic(hass, daily_cost, "RM")
    _seed_statistic(hass, daily_energy, "kWh")
    _seed_statistic(hass, other, "RM")
    await async_wait_recording_done(hass)

    entry = MockConfigEntry(domain=DOMAIN, version=2, data=_ENTRY_DATA)
    entry.add_to_hass(hass)

    await _async_relabel_currency(hass, entry)
    await async_wait_recording_done(hass)

    assert await _statistics_units(
        hass, {cost, due, usage, daily_cost, daily_energy, other}
    ) == {
        cost: "MYR",
        due: "MYR",
        usage: "kWh",
        daily_cost: "MYR",
        daily_energy: "kWh",
        other: "RM",
    }



async def test_relabel_before_2025_11(hass: HomeAssistant) -> None:
    """Before 2025.11 the recorder's own method relabels, without a unit class."""
    instance = MagicMock()
    instance.async_add_executor_job = AsyncMock(
        return_value={"sensor.cost": (1, {"unit_of_measurement": "RM"})}
    )

    with (
        patch("custom_components.mytnb.statistics.get_instance", return_value=instance),
        patch(
            "custom_components.mytnb.statistics.async_update_statistics_metadata", None
        ),
    ):
        await async_relabel_currency(hass, {"sensor.cost"})

    instance.async_update_statistics_metadata.assert_called_once_with(
        "sensor.cost", new_unit_of_measurement="MYR"
    )
