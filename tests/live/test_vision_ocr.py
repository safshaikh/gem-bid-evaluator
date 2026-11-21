"""Live multimodal vision integration tests for scanned PDF ingestion."""

import os
from pathlib import Path
import pytest

from app.config import get_api_key
from app.rules import evaluate
from app.schemas import Criterion, RuleType, Verdict
from app.vision_client import extract_bidder_evidence_vision

RUN_LIVE = os.environ.get("RUN_LIVE") == "1"
FIXTURES_DIR = Path("fixtures")
CLEAN_SCAN_PDF = FIXTURES_DIR / "bidder_scanned_clean.pdf"
BLURRY_SCAN_PDF = FIXTURES_DIR / "bidder_scanned_blurry.pdf"


@pytest.mark.skipif(not RUN_LIVE, reason="Live test requires RUN_LIVE=1")
def test_clean_scan_extracts_turnover_and_oem_live():
    """Clean scan extracts turnover and OEM status without 'REVIEW (no text layer)'."""
    if not CLEAN_SCAN_PDF.is_file():
        pytest.skip(f"Fixture {CLEAN_SCAN_PDF} not found")

    key = get_api_key()
    if not key:
        pytest.skip("No Gemini API key configured")

    criteria = [
        Criterion(
            id="avg_turnover",
            title="Annual Turnover",
            rule_type=RuleType.MIN_AVG_VALUE.value,
            threshold=5000000.0,
            unit="INR",
            source_doc="tender.pdf",
            source_page=1,
            source_quote="Annual turnover",
        ),
        Criterion(
            id="oem_authorisation",
            title="OEM Authorization",
            rule_type=RuleType.OEM_OR_AUTHORISED.value,
            source_doc="tender.pdf",
            source_page=1,
            source_quote="OEM authorization",
        ),
    ]

    pdf_bytes = CLEAN_SCAN_PDF.read_bytes()
    evidence = extract_bidder_evidence_vision(pdf_bytes, "CleanScannedBidder", criteria)

    assert len(evidence.fields) > 0, "Vision should extract fields from clean scan"
    assert any(f.source_kind == "vision" for f in evidence.fields)

    # Check OEM authorisation document was identified
    oem_docs = [d for d in evidence.documents_present if "oem" in d.doc_type.lower()]
    assert len(oem_docs) > 0, "Clean scan should detect OEM authorization document"

    # Evaluate rules: should PASS on OEM and not return "no text layer"
    oem_res = evaluate(criteria[1], evidence)
    assert oem_res.verdict == Verdict.PASS
    assert "no readable text layer" not in oem_res.reason.lower()


@pytest.mark.skipif(not RUN_LIVE, reason="Live test requires RUN_LIVE=1")
def test_blurry_scan_never_yields_fail_live():
    """Deliberately blurry/rotated scan ends in REVIEW, never FAIL."""
    if not BLURRY_SCAN_PDF.is_file():
        pytest.skip(f"Fixture {BLURRY_SCAN_PDF} not found")

    key = get_api_key()
    if not key:
        pytest.skip("No Gemini API key configured")

    criteria = [
        Criterion(
            id="avg_turnover",
            title="Annual Turnover",
            rule_type=RuleType.MIN_AVG_VALUE.value,
            threshold=5000000.0,
            unit="INR",
            source_doc="tender.pdf",
            source_page=1,
            source_quote="Annual turnover",
        ),
    ]

    pdf_bytes = BLURRY_SCAN_PDF.read_bytes()
    evidence = extract_bidder_evidence_vision(pdf_bytes, "BlurryBidder", criteria)

    res = evaluate(criteria[0], evidence)
    # Critical invariant: must be REVIEW, never FAIL
    assert res.verdict != Verdict.FAIL
    assert res.verdict == Verdict.REVIEW
    assert res.speaking_order_line is None


@pytest.mark.skipif(not RUN_LIVE, reason="Live test requires RUN_LIVE=1")
def test_vision_extraction_stability_live():
    """10-run stability test measuring dual extraction agreement rate."""
    if not CLEAN_SCAN_PDF.is_file():
        pytest.skip(f"Fixture {CLEAN_SCAN_PDF} not found")

    key = get_api_key()
    if not key:
        pytest.skip("No Gemini API key configured")

    criteria = [
        Criterion(
            id="avg_turnover",
            title="Annual Turnover",
            rule_type=RuleType.MIN_AVG_VALUE.value,
            threshold=5000000.0,
            unit="INR",
            source_doc="tender.pdf",
            source_page=1,
            source_quote="Annual turnover",
        ),
    ]

    pdf_bytes = CLEAN_SCAN_PDF.read_bytes()
    agreed_runs = 0
    total_runs = 10

    for i in range(total_runs):
        evidence = extract_bidder_evidence_vision(pdf_bytes, f"StabilityBidder_{i}", criteria)
        # Check if fields guard passed (dual extraction agreed)
        if any(f.guard_passed and not f.disputed for f in evidence.fields):
            agreed_runs += 1

    agreement_rate = (agreed_runs / total_runs) * 100
    print(f"\nMeasured 10-run vision agreement rate: {agreement_rate:.1f}% ({agreed_runs}/{total_runs})")
    assert agreed_runs >= 8, f"Agreement rate too low: {agreed_runs}/{total_runs}"

