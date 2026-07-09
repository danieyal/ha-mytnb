"""Bounded retry with exponential backoff for the integration's API calls.

python-mytnb already retries each individual HTTP request against the myTNB
API (which sits behind CloudFront/WAF and intermittently returns transient
errors). This helper adds a second, higher-level retry around the
coordinator's operations (account discovery, per-account data fetch) so that
a transient failure which slipped past the library's per-request retries gets
a bounded second chance with the same exponential-with-jitter cadence, rather
than immediately marking the entity unavailable or forcing a full cycle until
the next poll interval.

Non-retryable errors — authentication failures, rate limiting, geo-blocks,
and non-transient API errors — propagate immediately. This mirrors the
library's own retry classification so the two layers stay consistent.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from mytnb.exceptions import APIError

# Transport-level errors that are always safe to retry. httpx is a hard
# dependency of python-mytnb; curl_cffi transport errors only surface from
# the legacy ASMX path, so its import is guarded to avoid a hard dependency
# here.
_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    asyncio.TimeoutError,
)

try:  # httpx is a hard dependency of python-mytnb and thus always present
    import httpx

    _RETRYABLE_EXCEPTIONS += (httpx.TransportError, httpx.TimeoutException)
except ImportError:
    pass

try:  # curl_cffi is only used by the legacy ASMX path; guard the import
    from curl_cffi.requests.exceptions import (
        RequestException as CurlRequestException,
    )

    _RETRYABLE_EXCEPTIONS += (CurlRequestException,)
except ImportError:
    pass


def _is_retryable(err: Exception) -> bool:
    """Return True if the error is a transient failure worth retrying."""
    if isinstance(err, _RETRYABLE_EXCEPTIONS):
        return True
    return isinstance(err, APIError) and getattr(err, "retryable", False)


async def with_retry[T](
    send: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    base_delay: float,
    backoff_factor: float = 2.0,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    logger: logging.Logger | None = None,
) -> T:
    """Call ``send`` with exponential backoff + jitter on transient failures.

    ``send`` is a zero-arg coroutine factory: each call performs one attempt.
    The delay before a retry is ``base_delay * backoff_factor**attempt`` plus a
    uniform jitter in ``[0, base_delay]`` (mirroring python-mytnb's cadence).

    Args:
        send: Zero-arg coroutine factory performing one attempt.
        attempts: Maximum number of attempts (including the first).
        base_delay: Base backoff delay in seconds (with added jitter).
        backoff_factor: Multiplier applied per attempt to grow the delay.
        sleep: Awaitable used to pause between attempts; defaults to
            ``asyncio.sleep`` and resolved at call time so tests can patch the
            module-level ``asyncio.sleep``.
        logger: Optional logger for debug messages between retries.

    Returns:
        Whatever ``send`` returns on the first successful attempt.

    Raises:
        ValueError: If ``attempts`` < 1, ``base_delay`` < 0, or
            ``backoff_factor`` < 1.
        The last exception raised by ``send`` once attempts are exhausted, or
        immediately for any non-retryable error.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    if base_delay < 0:
        raise ValueError(f"base_delay must be >= 0, got {base_delay}")
    if backoff_factor < 1:
        raise ValueError(f"backoff_factor must be >= 1, got {backoff_factor}")
    if sleep is None:
        sleep = asyncio.sleep

    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await send()
        except Exception as err:  # noqa: BLE001 - re-raised below unless retryable
            last_exc = err
            if attempt >= attempts - 1 or not _is_retryable(err):
                raise
            delay = base_delay * (backoff_factor**attempt) + random.uniform(
                0, base_delay
            )
            if logger is not None:
                logger.debug(
                    "Transient failure (attempt %d/%d), retrying in %.2fs: %s",
                    attempt + 1,
                    attempts,
                    delay,
                    err,
                )
            await sleep(delay)
    # Unreachable: the loop either returns or raises on the final attempt.
    assert last_exc is not None
    raise last_exc
