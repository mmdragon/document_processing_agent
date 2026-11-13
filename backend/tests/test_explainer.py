"""Mock explainer, guardrails, fallback for misbehaving explainers, and review reports."""

import json
import re
from pathlib import Path

import pytest

from app.agents.guardrails import check_explanation
from app.agents.models import (
    ExplainerInput,
    ExplanationDraft,
    ExplanationItem,
    ExplanationSection,
)
from app.agents.service import explain_document
from app.dependencies import get_explainer
from app.main import create_app
from app.repositories.documents import DocumentRepository
from app.review import apply_corrections
from tests.conftest import upload

SAMPLES = Path(__file__).resolve().parent.parent / "sample_data"
ALL = sorted(p.stem for p in (SAMPLES / "invoices").glob("*.pdf"))
FORBIDDEN = re.compile(r"approv\w* (?:for )?payment|ok to pay|send money|wire|is a duplicate", re.I)


def processed(client, name: str) -> dict:
    data = (SAMPLES / "invoices" / f"{name}.pdf").read_bytes()
    doc_id = upload(client, f"{name}.pdf", data).json()["document_id"]
    return client.post(f"/api/documents/{doc_id}/process").json()


def explain(client, doc_id: str) -> dict:
    r = client.get(f"/api/documents/{doc_id}/explanation")
    assert r.status_code == 200
    return r.json()


def all_text(e: dict) -> str:
    parts = [e["summary"], *e["next_steps"]]
    parts += [i["text"] for s in e["sections"] for i in s["items"]]
    parts += [q["text"] for q in e["questions"]]
    return "\n".join(parts)


@pytest.mark.parametrize("name", ALL)
def test_mock_explanation_passes_guardrails_for_every_sample(client, name):
    doc = processed(client, name)
    e = explain(client, doc["document_id"])
    assert e["explainer"] == "mock"
    assert e["model_generated"] is False
    assert e["guardrails"] == {"passed": True, "violations": [], "fallback_used": False}
    text = all_text(e)
    assert not FORBIDDEN.search(text)
    assert "fraud" not in text.lower() or "not a finding of fraud" in text.lower()
    assert "cannot approve or schedule payment" in e["disclaimer"]
    kinds = {i["kind"] for s in e["sections"] for i in s["items"]}
    assert kinds <= {"fact", "interpretation"}
    assert all(q["kind"] == "question" for q in e["questions"])


def test_facts_restate_values_with_evidence(client):
    doc = processed(client, "inv01_normal")
    e = explain(client, doc["document_id"])
    assert e["summary"].startswith(
        "This is invoice QOG-2026-0142 from Quillfeather Office Goods with a total of 633.80 USD"
    )
    assert "All deterministic checks passed" in e["summary"]
    extracted = next(s for s in e["sections"] if s["title"] == "What was extracted")
    total = next(i for i in extracted["items"] if i["refs"] == ["total"])
    assert total["kind"] == "fact"
    assert total["evidence"][0]["page_number"] == 1
    assert "$633.80" in total["evidence"][0]["line"]
    assert e["questions"] == []


def test_mismatch_gets_labelled_interpretation(client):
    e = explain(client, processed(client, "inv04_arithmetic_mismatch")["document_id"])
    interp = [i for s in e["sections"] for i in s["items"] if i["kind"] == "interpretation"]
    assert any("763.70" in i["text"] and "736.70" in i["text"] for i in interp)
    assert "Compare the amounts with the original document." in e["next_steps"]


def test_missing_due_date_is_not_computed(client):
    e = explain(client, processed(client, "inv03_missing_due_date")["document_id"])
    text = all_text(e)
    assert "does not calculate due dates" in text
    # Invoice date 2026-03-12 + 30 days would be 2026-04-11; it must never appear.
    assert "2026-04-11" not in text


def test_ambiguous_date_becomes_a_question(client):
    e = explain(client, processed(client, "inv13_ambiguous_date")["document_id"])
    [q] = e["questions"]
    assert "04/05/2026" in q["text"]
    assert "2026-04-05 or 2026-05-04" in q["text"]


def test_duplicate_is_possible_not_fraud(client):
    first = processed(client, "inv01_normal")
    second = processed(client, "inv05_duplicate")
    e = explain(client, second["document_id"])
    text = all_text(e)
    assert "inv01_normal.pdf" in text
    assert "not evidence of wrongdoing" in text
    assert any("already processed" in q["text"] for q in e["questions"])
    assert first["document_id"] != second["document_id"]


def test_scan_without_text(client):
    e = explain(client, processed(client, "inv09_scanned")["document_id"])
    assert e["summary"].startswith("No text could be read")
    assert e["next_steps"][0].startswith("Install Tesseract")


def test_corrections_and_review_are_reflected(client):
    doc = processed(client, "inv13_ambiguous_date")
    doc_id = doc["document_id"]
    client.post(
        f"/api/documents/{doc_id}/corrections",
        json={"corrections": [{"field": "invoice_date", "value": "2026-04-05"}]},
    )
    client.post(f"/api/documents/{doc_id}/review", json={"note": "ok"})
    e = explain(client, doc_id)
    assert "dated 2026-04-05" in e["summary"]
    assert "marked it reviewed" in e["summary"]
    assert any("entered by a reviewer" in i["text"] for s in e["sections"] for i in s["items"])
    assert e["questions"] == []


# ----- guardrails -----


def _input(client, name="inv01_normal") -> ExplainerInput:
    doc = processed(client, name)
    app_client = client
    detail_json = app_client.get(f"/api/documents/{doc['document_id']}").json()
    from app.schemas.documents import DocumentDetail

    detail = DocumentDetail.model_validate(detail_json)
    return ExplainerInput(detail, apply_corrections(detail.fields, detail.corrections))


def _draft(*texts: str) -> ExplanationDraft:
    return ExplanationDraft(
        summary=texts[0],
        sections=[
            ExplanationSection(
                title="x", items=[ExplanationItem(kind="interpretation", text=t) for t in texts[1:]]
            )
        ],
        questions=[],
        next_steps=[],
    )


@pytest.mark.parametrize(
    "text, reason",
    [
        ("The total is 999.99 USD.", "amount 999.99"),
        ("The due date is 2026-04-01 or maybe 2026-04-11.", "date 2026-04-11"),
        ("This looks fraudulent.", "fraud"),
        ("This vendor may be committing fraud.", "fraud"),
        ("The invoice is approved for payment.", "approving"),
        ("It is OK to pay this invoice.", "OK to pay"),
        ("Please send the money now.", "sending money"),
        ("This is a duplicate of the earlier invoice.", "duplicate as fact"),
    ],
)
def test_guardrails_catch_violations(client, text, reason):
    violations = check_explanation(_draft("Summary.", text), _input(client))
    assert violations and any(reason in v for v in violations), violations


def test_guardrails_allow_grounded_text(client):
    ok = _draft(
        "Invoice QOG-2026-0142 totals 633.80 USD (subtotal 585.50, tax 48.30) dated 2026-03-02.",
        "This is a possible duplicate; it is a similarity flag, not a finding of fraud.",
        "Quantities like 10 and 6 are fine; amounts like 1,317.60 are checked.",
    )
    violations = check_explanation(ok, _input(client))
    # 1,317.60 belongs to a different invoice, so exactly that one is flagged.
    assert len(violations) == 1 and "1,317.60" in violations[0]


class HallucinatingExplainer:
    name = "fake-model"
    model_generated = True

    def explain(self, data):
        return _draft("The total is 1,000,000.00 USD and it is OK to pay.")


class CrashingExplainer:
    name = "crashy"
    model_generated = True

    def explain(self, data):
        raise RuntimeError("model timeout")


class GoodModelExplainer:
    name = "fake-good-model"
    model_generated = True

    def explain(self, data):
        return _draft(f"Invoice {data.effective.invoice_number.value} needs a quick look.")


@pytest.mark.parametrize("explainer", [HallucinatingExplainer(), CrashingExplainer()])
def test_bad_explainer_falls_back_to_mock(client, explainer):
    data = _input(client)
    e = explain_document(data.document, explainer)
    assert e.explainer == "mock"
    assert e.model_generated is False
    assert e.guardrails.fallback_used is True
    assert e.guardrails.passed is True
    assert e.guardrails.violations  # the rejected output's problems are recorded
    assert "1,000,000" not in e.summary


def test_good_model_output_is_kept_and_labelled(client):
    e = explain_document(_input(client).document, GoodModelExplainer())
    assert e.explainer == "fake-good-model"
    assert e.model_generated is True
    assert e.guardrails.fallback_used is False


def test_explanation_endpoint_uses_configured_explainer(settings, tmp_path):
    from fastapi.testclient import TestClient

    from app.config import get_settings

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_explainer] = lambda: HallucinatingExplainer()
    c = TestClient(app)
    doc = processed(c, "inv01_normal")
    e = explain(c, doc["document_id"])
    assert e["explainer"] == "mock" and e["guardrails"]["fallback_used"] is True


def test_explanation_has_no_side_effects(client, settings):
    doc = processed(client, "inv04_arithmetic_mismatch")
    before = DocumentRepository(settings.database_path).get_detail(doc["document_id"])
    explain(client, doc["document_id"])
    client.get(f"/api/documents/{doc['document_id']}/report?format=markdown")
    after = DocumentRepository(settings.database_path).get_detail(doc["document_id"])
    assert before == after


# ----- report -----


def test_report_json_uses_corrected_values_and_keeps_extracted(client):
    doc = processed(client, "inv04_arithmetic_mismatch")
    doc_id = doc["document_id"]
    client.post(
        f"/api/documents/{doc_id}/corrections",
        json={"corrections": [{"field": "total", "value": "736.70", "note": "typo on invoice"}]},
    )
    r = client.get(f"/api/documents/{doc_id}/report")
    assert r.status_code == 200
    rep = r.json()
    total = next(f for f in rep["fields"] if f["field"] == "total")
    assert total == {
        "field": "total",
        "label": "Total",
        "value": "736.70",
        "source": "corrected",
        "extracted_value": "763.70",
        "evidence": total["evidence"],
    }
    assert total["evidence"]["page_number"] == 1
    discount = next(f for f in rep["fields"] if f["field"] == "discount")
    assert discount["source"] == "missing" and discount["value"] is None
    assert rep["issues"] == []
    assert len(rep["corrections"]) == 1
    assert rep["explanation"]["explainer"] == "mock"
    assert "synthetic" in rep["notice"].lower()


def test_report_markdown_download(client):
    doc = processed(client, "inv13_ambiguous_date")
    r = client.get(f"/api/documents/{doc['document_id']}/report?format=markdown")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.headers["content-disposition"] == (
        f'attachment; filename="review-{doc["document_id"]}.md"'
    )
    md = r.text
    assert md.startswith("# Invoice review: inv13_ambiguous_date.pdf")
    assert "| Invoice date | 04/05/2026 | unresolved |" in md
    assert "`ambiguous_date`" in md
    assert "_Question:_" in md
    assert "cannot approve or schedule payment" in md


def test_report_requires_processing(client):
    data = (SAMPLES / "invoices" / "inv01_normal.pdf").read_bytes()
    doc_id = upload(client, "a.pdf", data).json()["document_id"]
    assert client.get(f"/api/documents/{doc_id}/report").status_code == 409
    assert (
        client.get(f"/api/documents/{doc_id}/explanation")
        .json()["summary"]
        .startswith("This document has not been processed yet")
    )
    assert client.get(f"/api/documents/{doc_id}/report?format=pdf").status_code == 422


def test_ground_truth_files_unchanged_by_reporting(client):
    before = {p.name: p.read_bytes() for p in (SAMPLES / "ground_truth").glob("*.json")}
    doc = processed(client, "inv01_normal")
    client.get(f"/api/documents/{doc['document_id']}/report?format=markdown")
    after = {p.name: p.read_bytes() for p in (SAMPLES / "ground_truth").glob("*.json")}
    assert before == after
    assert json.loads(next(iter(after.values())))["synthetic"] is True
