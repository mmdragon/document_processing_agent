"""Deterministic parsers for money, quantities, dates, currencies and keys.

They never guess: if text has more than one reasonable reading, they say so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
CURRENCY_CODES = {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "MXN", "NZD"}

_NUMBER_CHARS = re.compile(r"[^0-9.,]")


def parse_number(text: str) -> Decimal | None:
    """Parse '1,234.56', '1.234,56', '6.5', '0,18', '2400', '-$165.00', '(12.00)'.

    The last '.' or ',' is the decimal separator only if 1-2 digits follow it;
    otherwise separators are treated as thousands grouping.
    """
    if not text:
        return None
    s = text.strip()
    negative = s.startswith("-") or s.startswith("−") or (s.startswith("(") and s.endswith(")"))
    s = _NUMBER_CHARS.sub("", s)
    if not s or not any(ch.isdigit() for ch in s):
        return None
    last_sep = max(s.rfind("."), s.rfind(","))
    if last_sep != -1 and 1 <= len(s) - last_sep - 1 <= 2:
        integer = re.sub(r"[.,]", "", s[:last_sep])
        normalized = f"{integer or '0'}.{s[last_sep + 1 :]}"
    else:
        normalized = re.sub(r"[.,]", "", s)
    try:
        value = Decimal(normalized)
    except InvalidOperation:
        return None
    return -value if negative else value


def detect_currency(text: str) -> str | None:
    """Return an ISO code if the text names one explicitly or uses a symbol."""
    for code in re.findall(r"\b[A-Z]{3}\b", text):
        if code in CURRENCY_CODES:
            return code
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    return None


def has_explicit_currency_code(text: str) -> bool:
    return any(code in CURRENCY_CODES for code in re.findall(r"\b[A-Z]{3}\b", text))


@dataclass
class ParsedDate:
    value: date | None
    status: str  # "found" | "ambiguous" | "unparseable"
    candidates: list[date] = field(default_factory=list)


_WEEKDAY = re.compile(
    r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)"
    r"\.?,?\s+",
    re.IGNORECASE,
)
_ORDINAL = re.compile(r"\b(\d{1,2})(st|nd|rd|th)\b", re.IGNORECASE)
_NUMERIC = re.compile(r"^(\d{1,4})([/.\-])(\d{1,2})\2(\d{1,4})$")
_TEXT_FORMATS = (
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
    "%d %B %Y",
    "%d %b %Y",
    "%d %B, %Y",
    "%d-%b-%Y",
    "%d-%B-%Y",
)


def parse_date(text: str) -> ParsedDate:
    """Parse a printed date. Numeric day/month orders that can't be told apart are ambiguous."""
    s = text.strip()
    m = _NUMERIC.match(s)
    if m:
        a, _sep, b, c = m.groups()
        if len(a) == 4:  # YYYY-MM-DD or YYYY/MM/DD
            return _single(int(a), int(b), int(c))
        if len(c) != 4:
            return ParsedDate(None, "unparseable")  # two-digit years are not guessed
        first, second, year = int(a), int(b), int(c)
        day_first = _safe_date(year, second, first)
        month_first = _safe_date(year, first, second)
        options = [d for d in (month_first, day_first) if d is not None]
        unique = sorted(set(options))
        if len(unique) == 1:
            return ParsedDate(unique[0], "found")
        if len(unique) == 2:
            return ParsedDate(None, "ambiguous", unique)
        return ParsedDate(None, "unparseable")

    s = _WEEKDAY.sub("", s)
    s = _ORDINAL.sub(r"\1", s)
    s = re.sub(r"\bof\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"(?<=[A-Za-z])\.", "", s)  # "Feb." -> "Feb"
    s = re.sub(r"\s+", " ", s).replace(" ,", ",").strip()
    for fmt in _TEXT_FORMATS:
        try:
            return ParsedDate(datetime.strptime(s, fmt).date(), "found")
        except ValueError:
            continue
    return ParsedDate(None, "unparseable")


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _single(year: int, month: int, day: int) -> ParsedDate:
    d = _safe_date(year, month, day)
    return ParsedDate(d, "found") if d else ParsedDate(None, "unparseable")


_VENDOR_SUFFIXES = {
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "co",
    "company",
    "corp",
    "corporation",
    "plc",
    "gmbh",
    "sarl",
    "sa",
    "bv",
    "the",
}


def vendor_key(name: str | None) -> str | None:
    """Normalize a vendor name for duplicate matching ('Acme, Inc.' == 'ACME')."""
    if not name:
        return None
    words = re.findall(r"[a-z0-9]+", name.lower().replace("&", " and "))
    words = [w for w in words if w not in _VENDOR_SUFFIXES]
    return " ".join(words) or None


def invoice_number_key(number: str | None) -> str | None:
    """Normalize an invoice number for duplicate matching ('qog 2026-0142' == 'QOG20260142')."""
    if not number:
        return None
    key = re.sub(r"[^A-Z0-9]", "", number.upper())
    return key or None
