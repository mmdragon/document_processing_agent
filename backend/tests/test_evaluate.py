"""The evaluation script itself: text-layer samples must score perfectly."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import evaluate  # noqa: E402


def test_text_layer_samples_score_perfectly():
    results = evaluate.evaluate(use_ocr=False)
    assert len(results) == 14
    assert evaluate.text_layer_failures(results) == 0
    text = [r for r in results if r.method != "none"]
    assert len(text) == 12
    assert all(r.fields_correct == len(r.fields) and r.line_items_correct for r in text)


def test_scans_are_reported_not_hidden():
    results = {r.document_id: r for r in evaluate.evaluate(use_ocr=False)}
    for doc_id in ("inv09_scanned", "inv11_low_quality_scan"):
        r = results[doc_id]
        assert r.method == "none"
        assert "ocr_required" in r.found_issues
        assert any(f.outcome == "missed" for f in r.fields)
    # low_quality_scan needs OCR confidence, which is not implemented: reported as missed.
    assert results["inv11_low_quality_scan"].missed_issues == ["low_quality_scan"]


def test_cli_writes_markdown_and_json(tmp_path, capsys):
    out = tmp_path / "eval.json"
    assert evaluate.main(["--json", str(out)]) == 0
    md = capsys.readouterr().out
    assert md.startswith("# Ground-truth evaluation")
    assert "| Text-layer PDFs | 12 | 156/156 (100%) | 12/12 (100%) | 0 | 0 |" in md
    data = json.loads(out.read_text())
    assert len(data) == 14 and data[0]["document_id"] == "inv01_normal"
