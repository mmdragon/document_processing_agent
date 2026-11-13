"""Run an explainer with guardrails, falling back to the mock on any violation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.agents.guardrails import check_explanation
from app.agents.mock import MockExplainer
from app.agents.models import (
    AgentExplainer,
    ExplainerInput,
    Explanation,
    GuardrailReport,
)
from app.review import apply_corrections
from app.schemas.documents import DocumentDetail

logger = logging.getLogger(__name__)


def get_explainer(mode: str) -> AgentExplainer:
    """Only the mock is implemented. Hosted models need an explicit, costed opt-in."""
    if mode != "mock":
        logger.warning("explainer mode %r is not available; using the mock explainer", mode)
    return MockExplainer()


def explain_document(detail: DocumentDetail, explainer: AgentExplainer) -> Explanation:
    effective = (
        apply_corrections(detail.fields, detail.corrections) if detail.fields is not None else None
    )
    data = ExplainerInput(document=detail, effective=effective)

    rejected: list[str] = []
    if not isinstance(explainer, MockExplainer):
        try:
            draft = explainer.explain(data)
            rejected = check_explanation(draft, data)
        except Exception as exc:  # a broken explainer must not break the review page
            logger.warning("explainer %s failed: %s", explainer.name, type(exc).__name__)
            rejected = [f"explainer error: {type(exc).__name__}"]
        if not rejected:
            return _finish(draft, explainer, GuardrailReport(passed=True, violations=[]))
        logger.warning(
            "explainer %s output rejected for document %s (%d violations); using mock",
            explainer.name,
            detail.document_id,
            len(rejected),
        )

    mock = MockExplainer()
    draft = mock.explain(data)
    violations = check_explanation(draft, data)
    report = GuardrailReport(
        passed=not violations,
        violations=rejected + violations,
        fallback_used=bool(rejected),
    )
    return _finish(draft, mock, report)


def _finish(draft, explainer: AgentExplainer, report: GuardrailReport) -> Explanation:
    return Explanation(
        **draft.model_dump(),
        explainer=explainer.name,
        model_generated=explainer.model_generated,
        guardrails=report,
        generated_at=datetime.now(UTC),
    )
