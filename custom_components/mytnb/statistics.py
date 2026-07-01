"""Long-term statistics backfill for myTNB daily usage.

The myTNB API returns roughly the past 30 days of daily consumption (kWh) and
cost (RM). Home Assistant cannot backfill raw entity *state* history, but it can
import long-term *statistics* with historical timestamps. We publish the daily
series as external statistics (``mytnb:<account>_daily_energy`` /
``..._daily_cost``) so history shows up immediately on install and the energy
series is usable in the Energy dashboard.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData, StatisticMetaData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CURRENCY_RM = "RM"

# Daily readings are Malaysian local days; anchor buckets to KL midnight.
_TZ = dt_util.get_time_zone("Asia/Kuala_Lumpur")


def _iter_days(usage: Any) -> Iterator[Any]:
    """Yield every DailyUsage across all week ranges."""
    for week in usage.by_day:
        yield from week.days


def _day_start(day: Any) -> datetime | None:
    """Return the tz-aware midnight (Asia/Kuala_Lumpur) for a daily reading."""
    try:
        return datetime(int(day.year), int(day.month), int(day.day), tzinfo=_TZ)
    except (AttributeError, TypeError, ValueError):
        parsed = dt_util.parse_date(getattr(day, "date", "") or "")
        if parsed is None:
            return None
        return datetime(parsed.year, parsed.month, parsed.day, tzinfo=_TZ)


async def async_import_daily_statistics(
    hass: HomeAssistant,
    account_number: str,
    owner_name: str,
    usage: Any,
) -> None:
    """Import daily energy and cost statistics for one account.

    Idempotent: only days newer than what has already been imported are added,
    so calling this every poll cycle is cheap.
    """
    days = sorted(
        (
            day
            for day in _iter_days(usage)
            if not getattr(day, "is_missing_reading", False)
        ),
        key=lambda day: day.date,
    )
    if not days:
        return

    label = owner_name or account_number
    await _import_series(
        hass,
        account_number,
        days,
        suffix="energy",
        name=f"{label} daily energy",
        unit=UnitOfEnergy.KILO_WATT_HOUR,
        value_fn=lambda day: day.consumption_kwh,
    )
    await _import_series(
        hass,
        account_number,
        days,
        suffix="cost",
        name=f"{label} daily cost",
        unit=CURRENCY_RM,
        value_fn=lambda day: day.amount_rm,
    )


async def _import_series(
    hass: HomeAssistant,
    account_number: str,
    days: list[Any],
    *,
    suffix: str,
    name: str,
    unit: str,
    value_fn: Callable[[Any], float],
) -> None:
    """Compute cumulative sums for new days and import them as statistics."""
    statistic_id = f"{DOMAIN}:{account_number}_daily_{suffix}"

    last = await get_instance(hass).async_add_executor_job(
        get_last_statistics, hass, 1, statistic_id, True, {"sum"}
    )

    total = 0.0
    last_start_ts: float | None = None
    rows = last.get(statistic_id) if last else None
    if rows:
        total = rows[0].get("sum") or 0.0
        last_start_ts = _as_timestamp(rows[0].get("start"))

    statistics: list[StatisticData] = []
    for day in days:
        start = _day_start(day)
        if start is None:
            continue
        # Skip days already imported (strictly-new days only).
        if last_start_ts is not None and start.timestamp() <= last_start_ts:
            continue
        value = value_fn(day)
        total += value
        statistics.append(StatisticData(start=start, state=value, sum=total))

    if not statistics:
        return

    metadata = StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=name,
        source=DOMAIN,
        statistic_id=statistic_id,
        unit_of_measurement=unit,
    )
    async_add_external_statistics(hass, metadata, statistics)
    _LOGGER.debug(
        "Imported %d %s statistics for account %s",
        len(statistics),
        suffix,
        account_number,
    )


def _as_timestamp(value: Any) -> float | None:
    """Normalise a statistics ``start`` (float ts or datetime) to a timestamp."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return value.timestamp()
