"""Output guardrails for explainers.

Checks run on every explanation, including the mock, so that a future model-backed
explainer is held to the same rules:

1. No invented values: every money amount (n.nn) and ISO date in the text must already
   appear in the document's extracted data, check results, or corrections.
2. No fraud labels: "fraud" may only appear in an explicit negation.
3. No payment actions: no approving, authorising, paying, sending or wiring money.
4. Duplicates stay "possible": never "is a duplicate" / "confirmed duplicate".
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from app.agents.models import ExplainerInput, ExplanationDraft

_MONEY = re.compile(r"(?<![\d.])\d{1,3}(?:,\d{3})*\.\d{2}(?![\d])|(?<![\d.,])\d+\.\d{2}(?![\d])")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

_FRAUD = re.compile(r"\bfraud\w*", re.IGNORECASE)
_FRAUD_NEGATED = re.compile(
    r"\bnot\s+(?:a\s+finding\s+of|evidence\s+of|an\s+indication\s+of|a\s+sign\s+of)\s+fraud\b",
    re.IGNORECASE,
)
_FORBIDDEN: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r"\b(?:approve[ds]?|approving|authori[sz]e[ds]?|authori[sz]ing)\b[^.]{0,40}\bpayments?\b",
            re.IGNORECASE,
        ),
        "mentions approving or authorising payment",
    ),
    (
        re.compile(r"\b(?:ok|okay|cleared|good)\s+to\s+pay\b", re.IGNORECASE),
        "says the invoice is OK to pay",
    ),
    (
        re.compile(
            r"\b(?:pay|send|wire|transfer|remit)\b[^.]{0,20}\b(?:now|immediately|funds|money)\b",
            re.IGNORECASE,
        ),
        "instructs sending money",
    ),
    (
        re.compile(
            r"\b(?:is|are)\s+(?:a\s+|an\s+)?(?:confirmed\s+|definite\s+|definitely\s+)?duplicates?\b"
            r"|\bconfirmed\s+duplicate\b",
            re.IGNORECASE,
        ),
        "states a duplicate as fact instead of 'possible duplicate'",
    ),
]


def _money_key(text: str) -> str | None:
    try:
        return str(Decimal(text.replace(",", "")).quantize(Decimal("0.01")))
    except InvalidOperation:
        return None


def _allowed_values(data: ExplainerInput) -> tuple[set[str], set[str]]:
    blob = data.document.model_dump_json()
    if data.effective is not None:
        blob += data.effective.model_dump_json()
    money = {k for m in _MONEY.findall(blob) if (k := _money_key(m))}
    dates = set(_ISO_DATE.findall(blob))
    return money, dates


def _all_text(draft: ExplanationDraft) -> list[str]:
    texts = [draft.summary, *draft.next_steps]
    texts += [i.text for s in draft.sections for i in s.items]
    texts += [q.text for q in draft.questions]
    return texts


def check_explanation(draft: ExplanationDraft, data: ExplainerInput) -> list[str]:
    """Return a list of violations (empty when the draft is acceptable)."""
    money_ok, dates_ok = _allowed_values(data)
    violations: list[str] = []
    for text in _all_text(draft):
        for m in _MONEY.findall(text):
            key = _money_key(m)
            if key is not None and key not in money_ok:
                violations.append(f"amount {m} does not appear in the document data: {text!r}")
        for d in _ISO_DATE.findall(text):
            if d not in dates_ok:
                violations.append(f"date {d} does not appear in the document data: {text!r}")
        without_negations = _FRAUD_NEGATED.sub("", text)
        if _FRAUD.search(without_negations):
            violations.append(f"labels something as fraud: {text!r}")
        for pattern, reason in _FORBIDDEN:
            if pattern.search(text):
                violations.append(f"{reason}: {text!r}")
    return violations
