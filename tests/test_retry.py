"""Tests for the retry/backoff helper in custom_components/mytnb/retry.py."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest
from mytnb.exceptions import (
    APIError,
    AuthenticationError,
    GeoBlockedError,
    MyTNBError,
    RateLimitError,
)

from custom_components.mytnb.retry import _is_retryable, with_retry


def _noop_sleep() -> AsyncMock:
    """Return an awaitable sleep mock that records calls and never blocks."""
    return AsyncMock(return_value=None)


def test_is_retryable_api_error_only_when_flagged() -> None:
    """An APIError is retryable iff its ``retryable`` flag is set."""
    assert _is_retryable(APIError("blip", retryable=True)) is True
    assert _is_retryable(APIError("permanent", retryable=False)) is False


def test_is_retryable_transient_transport_error() -> None:
    """Asyncio/transport timeouts are always retryable."""
    assert _is_retryable(TimeoutError()) is True


def test_is_retryable_not_for_auth_rate_limit_or_geo_block() -> None:
    """Auth, rate-limit, geo-block and plain MyTNB errors never retry."""
    assert _is_retryable(AuthenticationError("bad creds")) is False
    assert _is_retryable(RateLimitError("slow down")) is False
    assert _is_retryable(GeoBlockedError()) is False
    assert _is_retryable(MyTNBError("mystery")) is False


def test_is_retryable_not_for_generic_exceptions() -> None:
    """Programming bugs and unrelated errors must surface immediately."""
    assert _is_retryable(ValueError("nope")) is False
    assert _is_retryable(RuntimeError("boom")) is False


async def test_with_retry_success_first_try() -> None:
    """A call that succeeds immediately is returned with no retries."""
    send = AsyncMock(return_value="ok")
    sleep = _noop_sleep()

    result = await with_retry(send, attempts=3, base_delay=0.5, sleep=sleep)

    assert result == "ok"
    send.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_with_retry_recovers_after_transient_failures() -> None:
    """A retryable error followed by success retries and returns the value."""
    send = AsyncMock(
        side_effect=[
            APIError("blip", retryable=True),
            APIError("blip again", retryable=True),
            "ok",
        ]
    )
    sleep = _noop_sleep()

    result = await with_retry(send, attempts=3, base_delay=0.5, sleep=sleep)

    assert result == "ok"
    assert send.await_count == 3
    assert sleep.await_count == 2  # two backoffs between three attempts


async def test_with_retry_non_retryable_propagates_immediately() -> None:
    """A non-retryable error re-raises on the first attempt, no backoff."""
    err = RuntimeError("permanent")
    send = AsyncMock(side_effect=err)
    sleep = _noop_sleep()

    with pytest.raises(RuntimeError, match="permanent"):
        await with_retry(send, attempts=3, base_delay=0.5, sleep=sleep)

    send.assert_awaited_once()
    sleep.assert_not_awaited()


async def test_with_retry_exhausts_attempts_and_reraises_last() -> None:
    """When all attempts fail with retryable errors, the last one re-raises."""
    errors = [APIError(f"blip {i}", retryable=True) for i in range(3)]
    send = AsyncMock(side_effect=errors)
    sleep = _noop_sleep()

    with pytest.raises(APIError, match="blip 2"):
        await with_retry(send, attempts=3, base_delay=0.5, sleep=sleep)

    assert send.await_count == 3  # exactly ``attempts`` tries
    assert sleep.await_count == 2


async def test_with_retry_backoff_grows_with_factor_and_sleeps() -> None:
    """Backoff delay scales as base_delay * factor**attempt and is awaited."""
    send = AsyncMock(
        side_effect=[
            APIError("blip", retryable=True),
            APIError("blip", retryable=True),
            "ok",
        ]
    )
    sleep = _noop_sleep()

    await with_retry(
        send, attempts=3, base_delay=1.0, backoff_factor=2.0, sleep=sleep
    )

    # attempt 0 → 1.0*2**0 = 1.0; attempt 1 → 1.0*2**1 = 2.0 (jitter in
    # [0, base_delay=1.0]).
    delays = [call.args[0] for call in sleep.await_args_list]
    assert len(delays) == 2
    assert 1.0 <= delays[0] <= 2.0  # 1.0 + jitter in [0, 1.0]
    assert 2.0 <= delays[1] <= 3.0  # 2.0 + jitter in [0, 1.0]


async def test_with_retry_default_sleep_is_asyncio_sleep() -> None:
    """Without an injected sleep, defaults to asyncio.sleep (smoke test)."""
    send = AsyncMock(return_value="ok")

    result = await with_retry(send, attempts=3, base_delay=0.0)

    assert result == "ok"
    send.assert_awaited_once()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"attempts": 0, "base_delay": 0.5, "backoff_factor": 2.0},  # attempts < 1
        {"attempts": 3, "base_delay": -0.1, "backoff_factor": 2.0},  # base_delay < 0
        {"attempts": 3, "base_delay": 0.5, "backoff_factor": 0.5},  # factor < 1
    ],
)
async def test_with_retry_rejects_invalid_args(kwargs) -> None:
    """Invalid retry parameters raise ValueError before the first attempt."""
    send = AsyncMock(return_value="ok")
    with pytest.raises(ValueError):
        await with_retry(send, **kwargs)
    send.assert_not_awaited()


async def test_with_retry_logs_between_attempts() -> None:
    """A debug log line is emitted for each retry when a logger is supplied."""
    send = AsyncMock(side_effect=[APIError("blip", retryable=True), "ok"])
    sleep = _noop_sleep()
    logger = logging.getLogger("test.with_retry")
    logger.setLevel(logging.DEBUG)

    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append  # type: ignore[method-assign]
    logger.addHandler(handler)
    try:
        await with_retry(
            send, attempts=3, base_delay=0.5, sleep=sleep, logger=logger
        )
    finally:
        logger.removeHandler(handler)

    retry_logs = [r for r in records if "retrying in" in r.getMessage()]
    assert len(retry_logs) == 1


async def test_with_retry_no_logger_does_not_crash() -> None:
    """Omitting the logger exercises the no-log path without error."""
    send = AsyncMock(side_effect=[APIError("blip", retryable=True), "ok"])
    result = await with_retry(send, attempts=3, base_delay=0.5, sleep=_noop_sleep())
    assert result == "ok"
