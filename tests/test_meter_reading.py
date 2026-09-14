"""Tests for bill-PDF meter-reading parsing."""

from custom_components.mytnb.meter_reading import _parse_meter_table


def test_parse_meter_table() -> None:
    """Extract all registers from the PDF's Maklumat Meter text."""
    text = """
    Bil Terperinci Anda
    Maklumat Meter
    No. Meter Dahulu Semasa Penggunaan Unit
    M SIE1052308047669 9,750 10,319 569 kWh
    M SIE1052308047669 76 81 5 kW
    M SIE1052308047669 1,174 1,265 91 kVARh
    Perlu Bantuan?
    """

    readings = _parse_meter_table(text)

    assert [(r.meter_number, r.unit) for r in readings] == [
        ("SIE1052308047669", "kWh"),
        ("SIE1052308047669", "kW"),
        ("SIE1052308047669", "kVARh"),
    ]
    assert readings[0].previous_reading == 9750.0
    assert readings[0].current_reading == 10319.0
    assert readings[0].usage == 569.0


def test_parse_meter_table_requires_meter_section() -> None:
    """Ignore meter-like text outside the PDF's meter-information section."""
    text = "M SIE1052308047669 9,750 10,319 569 kWh"

    assert _parse_meter_table(text) == []
