"""Fetch and parse real meter register readings from the bill PDF.

python-mytnb doesn't wrap ``GetBillMaskingPDFV2`` (the legacy ASMX endpoint the
myTNB app uses to fetch a bill's PDF), so this calls it directly through the
client's already-authenticated legacy transport. The PDF's "Maklumat Meter"
section carries the actual previous/current register readings — unlike the
smart-meter usage endpoints, which only ever return derived daily/monthly
consumption, never the underlying odometer-style reading.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import mytnb.client.config

if TYPE_CHECKING:
    import mytnb

_LOGGER = logging.getLogger(__name__)

# Matches a "Maklumat Meter" row, e.g.:
#   M SIE1052308047669   9,750   10,319   569   kWh
# The leading "M" marker and thousands separators are stripped/ignored.
_METER_ROW_RE = re.compile(
    r"M?\s*([A-Z0-9]{6,})\s+([\d,]+)\s+([\d,]+)\s+(\d+)\s+(kWh|kW|kVARh)\b"
)


@dataclass
class MeterRegisterReading:
    """A single meter register row (one of kWh/kW/kVARh) from a bill PDF."""

    meter_number: str
    previous_reading: float
    current_reading: float
    usage: float
    unit: str


async def fetch_meter_readings(
    client: mytnb.MyTNBClient,
    account: Any,
    billing_no: str,
) -> list[MeterRegisterReading]:
    """Fetch the bill PDF for ``billing_no`` and parse its meter register table.

    Returns an empty list if the bill has no masking PDF available (e.g. the
    account has no bill history yet) rather than raising, since this is
    best-effort bonus data layered on top of the core sensors.
    """
    data = {
        "apiKeyID": mytnb.client.config.DEFAULT_SECURE_KEY_K1,
        "contractAccount": account.account_number,
        "billingNo": billing_no,
        "isOwnerBill": account.is_owned_bool,
        "lang": "EN",
    }
    result = await client._legacy_transport.post("GetBillMaskingPDFV2", data)
    if not isinstance(result, dict):
        _LOGGER.debug("Unexpected GetBillMaskingPDFV2 response type: %s", type(result))
        return []

    binary_bill = result.get("binaryBill")
    if not binary_bill:
        return []

    pdf_bytes = base64.b64decode(binary_bill)
    text = await asyncio.to_thread(_extract_pdf_text, pdf_bytes)
    return _parse_meter_table(text)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract all text from the bill PDF (runs in a thread; pdfplumber is sync)."""
    import pdfplumber

    pages_text = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                pages_text.append(page_text)
    return "\n".join(pages_text)


def _parse_meter_table(text: str) -> list[MeterRegisterReading]:
    """Parse "Maklumat Meter" rows out of the bill's extracted text."""
    meter_section = text.partition("Maklumat Meter")[2]
    if not meter_section:
        return []

    readings = []
    for match in _METER_ROW_RE.finditer(meter_section):
        meter_number, previous, current, usage, unit = match.groups()
        readings.append(
            MeterRegisterReading(
                meter_number=meter_number,
                previous_reading=float(previous.replace(",", "")),
                current_reading=float(current.replace(",", "")),
                usage=float(usage.replace(",", "")),
                unit=unit,
            )
        )
    return readings
