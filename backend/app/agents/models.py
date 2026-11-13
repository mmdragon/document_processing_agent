"""Explainer input/output types.

The explainer only *describes* data the deterministic pipeline already produced. Every
item is labelled as a fact (restating extracted values or check results), an
interpretation (what an issue might mean), or a question for the reviewer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from pydantic import BaseModel

from app.schemas.documents import DocumentDetail
from app.schemas.invoice import Evidence, InvoiceFields

ItemKind = Literal["fact", "interpretation", "question"]

DISCLAIMER = (
    "This summary restates the deterministic checks and extracted values. It cannot "
    "approve or schedule payment, send money, contact vendors, or change the document."
)


class ExplanationItem(BaseModel):
    kind: ItemKind
    text: str
    refs: list[str] = []  # field names and/or issue codes this item is about
    evidence: list[Evidence] = []


class ExplanationSection(BaseModel):
    title: str
    items: list[ExplanationItem]


class ExplanationDraft(BaseModel):
    """What an explainer returns, before guardrails run."""

    summary: str
    sections: list[ExplanationSection]
    questions: list[ExplanationItem]
    next_steps: list[str]


class GuardrailReport(BaseModel):
    passed: bool
    violations: list[str]
    fallback_used: bool = False


class Explanation(ExplanationDraft):
    explainer: str
    model_generated: bool
    disclaimer: str = DISCLAIMER
    guardrails: GuardrailReport
    generated_at: datetime


@dataclass(frozen=True)
class ExplainerInput:
    document: DocumentDetail
    # Extracted fields with the latest reviewer corrections applied (None if unprocessed).
    effective: InvoiceFields | None


class AgentExplainer(Protocol):
    """explain(input) -> draft. Implementations must not have side effects."""

    name: str
    model_generated: bool

    def explain(self, data: ExplainerInput) -> ExplanationDraft: ...
