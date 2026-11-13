from datetime import date
from decimal import Decimal

import pytest

from app.normalization.parsers import (
    detect_currency,
    invoice_number_key,
    parse_date,
    parse_number,
    vendor_key,
)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("$1,317.60", "1317.60"),
        ("1.250,00 €", "1250.00"),
        ("-$165.00", "-165.00"),
        ("(12.00)", "-12.00"),
        ("6.5", "6.5"),
        ("0,18", "0.18"),
        ("2400", "2400"),
        ("1,250", "1250"),
        ("1 234,56 EUR", "1234.56"),
    ],
)
def test_parse_number(text, expected):
    assert parse_number(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["", "abc", "€", "--"])
def test_parse_number_rejects_non_numbers(text):
    assert parse_number(text) is None


@pytest.mark.parametrize(
    "text, expected",
    [
        ("March 2, 2026", date(2026, 3, 2)),
        ("Tuesday, 3rd February 2026", date(2026, 2, 3)),
        ("3rd of Feb. 2026", date(2026, 2, 3)),
        ("2026/03/05", date(2026, 3, 5)),
        ("2026-03-05", date(2026, 3, 5)),
        ("15.01.2026", date(2026, 1, 15)),
        ("03/15/2026", date(2026, 3, 15)),
        ("05/05/2026", date(2026, 5, 5)),
        ("12-Mar-2026", date(2026, 3, 12)),
    ],
)
def test_parse_date_found(text, expected):
    parsed = parse_date(text)
    assert parsed.status == "found"
    assert parsed.value == expected


def test_parse_date_ambiguous_is_not_guessed():
    parsed = parse_date("04/05/2026")
    assert parsed.status == "ambiguous"
    assert parsed.value is None
    assert parsed.candidates == [date(2026, 4, 5), date(2026, 5, 4)]


@pytest.mark.parametrize("text", ["2026-02-30", "04/05/26", "next Tuesday", ""])
def test_parse_date_unparseable(text):
    parsed = parse_date(text)
    assert parsed.status == "unparseable"
    assert parsed.value is None


def test_detect_currency_prefers_codes():
    assert detect_currency("Total (EUR)  1.825,00 €") == "EUR"
    assert detect_currency("Total  £40.00") == "GBP"
    assert detect_currency("Total  40.00") is None


def test_duplicate_keys_normalize():
    assert vendor_key("Quillfeather Office Goods, Inc.") == vendor_key("QUILLFEATHER OFFICE GOODS")
    assert vendor_key("Smith & Sons Co.") == "smith and sons"
    assert vendor_key("") is None
    assert invoice_number_key("qog 2026-0142") == invoice_number_key("QOG-2026-0142")
    assert invoice_number_key("--") is None
