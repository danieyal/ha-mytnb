"""Tests for statistics.py (daily energy/cost backfill)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.mytnb.statistics import _TZ, async_import_daily_statistics

ACCOUNT = "220123456789"


@dataclass
class FakeDay:
    """Minimal stand-in for mytnb.models.DailyUsage."""

    date: str
    year: str
    month: str
    day: str
    consumption_kwh: float
    amount_rm: float
    is_missing_reading: bool = False


@dataclass
class FakeWeek:
    days: list[FakeDay]


@dataclass
class FakeUsage:
    by_day: list[FakeWeek]


def _usage(days: list[FakeDay]) -> FakeUsage:
    return FakeUsage(by_day=[FakeWeek(days=days)])


def _patch_recorder(prior: dict | None = None):
    """Patch the recorder helpers used by statistics.py.

    ``prior`` maps a statistic_id to the dict get_last_statistics would return.
    """
    prior = prior or {}

    async def _last_stats(func, hass, number, statistic_id, convert, types):
        return prior.get(statistic_id, {})

    instance = MagicMock()
    instance.async_add_executor_job = AsyncMock(side_effect=_last_stats)

    add_stats = MagicMock()
    return (
        patch("custom_components.mytnb.statistics.get_instance", return_value=instance),
        patch(
            "custom_components.mytnb.statistics.async_add_external_statistics",
            add_stats,
        ),
        add_stats,
    )


async def test_first_import_energy_and_cost(hass: HomeAssistant) -> None:
    """First import backfills both series with cumulative sums, skipping gaps."""
    usage = _usage(
        [
            FakeDay("2026-05-13", "2026", "05", "13", 10.0, 2.0),
            FakeDay(
                "2026-05-14", "2026", "05", "14", 5.0, 1.0, is_missing_reading=True
            ),
            FakeDay("2026-05-15", "2026", "05", "15", 8.0, 3.0),
        ]
    )

    p_inst, p_add, add_stats = _patch_recorder()
    with p_inst, p_add:
        await async_import_daily_statistics(hass, ACCOUNT, "Alice", usage)

    assert add_stats.call_count == 2
    by_id = {
        call.args[1]["statistic_id"]: call.args[2] for call in add_stats.call_args_list
    }

    energy = by_id[f"mytnb:{ACCOUNT}_daily_energy"]
    assert [s["state"] for s in energy] == [10.0, 8.0]  # missing day skipped
    assert [s["sum"] for s in energy] == [10.0, 18.0]  # cumulative

    cost = by_id[f"mytnb:{ACCOUNT}_daily_cost"]
    assert [s["state"] for s in cost] == [2.0, 3.0]
    assert [s["sum"] for s in cost] == [2.0, 5.0]

    # Buckets are hour-aligned and timezone-aware.
    first = energy[0]["start"]
    assert (first.year, first.month, first.day) == (2026, 5, 13)
    assert first.tzinfo is not None
    assert first.minute == 0


async def test_incremental_import_only_new_days(hass: HomeAssistant) -> None:
    """Only days newer than the last stored bucket are imported, sum continues."""
    usage = _usage(
        [
            FakeDay("2026-05-13", "2026", "05", "13", 10.0, 2.0),
            FakeDay("2026-05-15", "2026", "05", "15", 8.0, 3.0),
            FakeDay("2026-05-16", "2026", "05", "16", 4.0, 1.5),
        ]
    )

    # Pretend 2026-05-15 (and everything up to sum 18.0 / 5.0) is already stored.
    day15_ts = _day_ts(2026, 5, 15)
    prior = {
        f"mytnb:{ACCOUNT}_daily_energy": {
            f"mytnb:{ACCOUNT}_daily_energy": [{"sum": 18.0, "start": day15_ts}]
        },
        f"mytnb:{ACCOUNT}_daily_cost": {
            f"mytnb:{ACCOUNT}_daily_cost": [{"sum": 5.0, "start": day15_ts}]
        },
    }

    p_inst, p_add, add_stats = _patch_recorder(prior)
    with p_inst, p_add:
        await async_import_daily_statistics(hass, ACCOUNT, "Alice", usage)

    by_id = {
        call.args[1]["statistic_id"]: call.args[2] for call in add_stats.call_args_list
    }

    energy = by_id[f"mytnb:{ACCOUNT}_daily_energy"]
    assert [s["state"] for s in energy] == [4.0]  # only 2026-05-16
    assert [s["sum"] for s in energy] == [22.0]  # 18.0 + 4.0

    cost = by_id[f"mytnb:{ACCOUNT}_daily_cost"]
    assert [s["sum"] for s in cost] == [6.5]  # 5.0 + 1.5


async def test_no_days_imports_nothing(hass: HomeAssistant) -> None:
    """Usage with no daily data imports nothing."""
    usage = _usage([])

    p_inst, p_add, add_stats = _patch_recorder()
    with p_inst, p_add:
        await async_import_daily_statistics(hass, ACCOUNT, "Alice", usage)

    add_stats.assert_not_called()


def _day_ts(year: int, month: int, day: int) -> float:
    return datetime(year, month, day, tzinfo=_TZ).timestamp()
